"""Anomaly flags. Flags never block anything; they sort to the top of review.

run_flags() recomputes every flag type from scratch. Unresolved flags whose
condition no longer holds are removed; resolved flags are kept as history.
"""

import re
from collections import defaultdict

from sqlmodel import Session, select

from .models import Category, Classification, Flag, RawTransaction, Setting
from .util import fy_of

CASH_RE = re.compile(r"cash\s*dep|\bcdm\b|by\s+cash|cash\s*deposit", re.I)


def _inr(p: int) -> str:
    return f"₹{p / 100:,.0f}"


def run_flags(s: Session) -> int:
    cfg = (s.get(Setting, "anomaly") or Setting(key="anomaly", value={})).value
    large = cfg.get("large_credit_paise", 50_000_00)
    repeat_min = cfg.get("round_repeat_min", 3)
    unit = cfg.get("round_unit_paise", 1_000_00)

    rows = s.exec(select(RawTransaction, Classification, Category)
                  .join(Classification, Classification.raw_transaction_id == RawTransaction.id, isouter=True)
                  .join(Category, Category.id == Classification.category_id, isouter=True)).all()

    want: dict[tuple[int, str], str] = {}

    for tx, _c, cat in rows:
        # Salary, redemptions, own transfers, loans and broker payouts are expected large credits.
        if tx.credit >= large and not (cat and cat.treatment in ("salary", "not_income", "trading_capital")):
            want[(tx.id, "large_credit")] = f"{_inr(tx.credit)} in one credit. Say where it came from."
        if tx.credit and (CASH_RE.search(tx.raw_description) or (cat and cat.name.startswith("Cash deposit"))):
            want[(tx.id, "cash_deposit")] = f"Cash deposit of {_inr(tx.credit)}. Keep proof of the cash source."

    # Two payments of the same amount on the same day with different bank references are
    # normal (e.g. two ₹900 UPI payments). A real duplicate is the SAME bank reference
    # appearing twice — e.g. one statement imported as both PDF and Excel.
    groups = defaultdict(list)
    for tx, _c, _ in rows:
        ref = re.sub(r"\s+", "", tx.ref_no or "").upper()
        if ref and ref not in {"-", "NA", "N/A"}:
            groups[(tx.account_id, tx.txn_date, tx.credit, tx.debit, ref)].append(tx)
    for txs in groups.values():
        if len(txs) > 1:
            for t in txs:
                want[(t.id, "possible_duplicate")] = (
                    f"Bank reference {t.ref_no} appears {len(txs)} times on {t.txn_date:%d-%m-%Y} for the same amount.")

    repeats = defaultdict(list)
    for tx, c, cat in rows:
        cp = c.counterparty if c else ""
        expected = cat is not None and cat.treatment in ("salary", "not_income", "trading_capital")
        if tx.credit and cp and tx.credit % unit == 0 and not expected:
            repeats[(fy_of(tx.txn_date), cp.lower(), tx.credit)].append(tx)
    for (fy, cp, amt), txs in repeats.items():
        if len(txs) >= repeat_min:
            for t in txs:
                want[(t.id, "round_repeat")] = (
                    f"{_inr(amt)} received {len(txs)} times from the same payer in FY {fy}. Explain the source.")

    existing = {(f.raw_transaction_id, f.type): f for f in s.exec(select(Flag))}
    for key, f in existing.items():
        if key not in want and not f.resolved:
            s.delete(f)
    added = 0
    for key, detail in want.items():
        f = existing.get(key)
        if f is None:
            s.add(Flag(raw_transaction_id=key[0], type=key[1], detail=detail))
            added += 1
        elif not f.resolved and f.detail != detail:
            f.detail = detail
            s.add(f)
    s.commit()
    return added
