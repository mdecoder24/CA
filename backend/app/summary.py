"""Read-side aggregates used by the dashboard, tax engine and reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from .models import Category, Classification, Flag, ImportBatch, RawTransaction, TaxInput
from .tax import engine
from .util import fy_range

HEAD_OF = {
    "salary": "Salary", "profession": "Business / Profession", "interest_savings": "Other sources",
    "interest_other": "Other sources", "dividend": "Other sources", "other_income": "Other sources",
    "gift_nonrelative": "Other sources", "gift_relative": "Exempt", "trading_capital": "Not income",
    "not_income": "Not income", "unexplained": "Needs explanation",
}


def fy_rows(s: Session, fy: str, account_id: Optional[int] = None):
    start, end = fy_range(fy)
    q = (select(RawTransaction, Classification, Category)
         .join(Classification, Classification.raw_transaction_id == RawTransaction.id, isouter=True)
         .join(Category, Category.id == Classification.category_id, isouter=True)
         .where(RawTransaction.txn_date >= start, RawTransaction.txn_date <= end)
         .order_by(RawTransaction.txn_date, RawTransaction.import_batch_id, RawTransaction.row_index))
    if account_id:
        q = q.where(RawTransaction.account_id == account_id)
    return s.exec(q).all()


def bank_aggregates(s: Session, fy: str) -> dict:
    """Rupee totals per treatment, confirmed only. Unconfirmed credits counted separately."""
    out: dict[str, float] = defaultdict(float)
    for tx, c, cat in fy_rows(s, fy):
        confirmed = c is not None and c.status == "confirmed" and cat is not None
        if tx.credit:
            if confirmed:
                out[cat.treatment] += tx.credit / 100
            else:
                out["unconfirmed_credits"] += tx.credit / 100
        elif tx.debit and confirmed and cat.treatment in ("business_expense", "tax_paid", "trading_capital"):
            out[f"{cat.treatment}_out" if cat.treatment == "trading_capital" else cat.treatment] += tx.debit / 100
    return dict(out)


def tax_estimate(s: Session, fy: str, profile_id: int = 1) -> dict:
    ti = s.exec(select(TaxInput).where(TaxInput.profile_id == profile_id, TaxInput.fy == fy)).first()
    return engine.compute(fy, bank_aggregates(s, fy), ti.data if ti else {})


def coverage_gaps(s: Session, fy: str, account_id: Optional[int] = None) -> list[dict]:
    """Per account: date ranges inside the FY (up to yesterday) not covered by any import."""
    from .banks import bank_name
    from .models import Account

    accounts = s.exec(select(Account)).all()
    if account_id:
        accounts = [a for a in accounts if a.id == account_id]
    out = []
    for a in accounts:
        if not s.exec(select(ImportBatch).where(ImportBatch.account_id == a.id)).first():
            continue
        for g in _gaps_for(s, fy, a.id):
            out.append({**g, "account_id": a.id, "account": a.nickname or bank_name(a.bank)})
    return out


def _gaps_for(s: Session, fy: str, account_id: int) -> list[dict]:
    start, end = fy_range(fy)
    # A statement downloaded today normally ends yesterday, so today is not a gap.
    end = min(end, date.fromordinal(date.today().toordinal() - 1))
    if end < start:
        return []
    batches = s.exec(select(ImportBatch).where(ImportBatch.period_from.is_not(None),
                                               ImportBatch.account_id == account_id)).all()
    spans = sorted((b.period_from, b.period_to) for b in batches if b.period_to >= start and b.period_from <= end)
    gaps, cursor = [], start
    for a, b in spans:
        if a > cursor:
            gaps.append({"from": cursor.isoformat(), "to": (a.fromordinal(a.toordinal() - 1)).isoformat()})
        if b >= cursor:
            cursor = b.fromordinal(b.toordinal() + 1)
    if cursor <= end:
        gaps.append({"from": cursor.isoformat(), "to": end.isoformat()})
    return gaps


def dashboard(s: Session, fy: str, account_id: Optional[int] = None) -> dict:
    rows = fy_rows(s, fy, account_id)
    credits = sum(tx.credit for tx, _, _ in rows)
    debits = sum(tx.debit for tx, _, _ in rows)
    unclassified_credits = [tx for tx, c, _ in rows if tx.credit and (c is None or c.status != "confirmed")]
    unclassified_debits = [tx for tx, c, _ in rows if tx.debit and (c is None or c.status != "confirmed")]
    months: dict[str, dict] = {}
    start, _ = fy_range(fy)
    for i in range(12):
        m = (start.month - 1 + i) % 12 + 1
        y = start.year + (start.month - 1 + i) // 12
        months[f"{y}-{m:02d}"] = {"month": f"{y}-{m:02d}", "credits": 0, "debits": 0}
    for tx, _, _ in rows:
        k = f"{tx.txn_date.year}-{tx.txn_date.month:02d}"
        months[k]["credits"] += tx.credit
        months[k]["debits"] += tx.debit

    heads: dict[str, int] = defaultdict(int)
    by_cat: dict[str, int] = defaultdict(int)
    for tx, c, cat in rows:
        if tx.credit:
            if c and c.status == "confirmed" and cat:
                heads[HEAD_OF.get(cat.treatment, "Other")] += tx.credit
                by_cat[cat.name] += tx.credit
            else:
                heads["Unconfirmed"] += tx.credit

    tx_ids = {tx.id for tx, _, _ in rows}
    open_flags = [f for f in s.exec(select(Flag).where(Flag.resolved == False)) if f.raw_transaction_id in tx_ids]  # noqa: E712
    # Closing balance = sum of each account's latest balance.
    last_by_acct: dict[int, int] = {}
    for tx, _, _ in rows:
        if tx.balance is not None:
            last_by_acct[tx.account_id] = tx.balance
    last_balance = sum(last_by_acct.values()) if last_by_acct else None
    return {
        "fy": fy,
        "total_credits": credits, "total_debits": debits, "closing_balance": last_balance,
        "txn_count": len(rows),
        "unclassified_credits": len(unclassified_credits),
        "unclassified_credit_amount": sum(t.credit for t in unclassified_credits),
        "unclassified_debits": len(unclassified_debits),
        "open_flags": len(open_flags),
        "monthly": list(months.values()),
        "income_heads": [{"head": k, "amount": v} for k, v in sorted(heads.items(), key=lambda x: -x[1])],
        "credit_categories": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
        "gaps": coverage_gaps(s, fy, account_id),
    }
