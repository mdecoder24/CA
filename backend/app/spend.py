"""Spend analytics and a spending-risk score.

"Spend" is money that actually left you: categorised expenses, business
expenses, and debits not yet categorised. Money only *moved* (own-account
transfers, investments, trading deposits, tax payments) is reported
separately and never counted as spend.

Confirmed and suggested categories are both used, so analytics work right
after an import; the response says how much of it rests on suggestions.

The risk score summarises cash-flow health from factual signals. It is a
reading aid, not financial advice.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from .models import Category, Classification, RawTransaction, Setting

SPEND_TREATMENTS = {"expense", "business_expense"}
MOVED_TREATMENTS = {"not_income", "trading_capital", "tax_paid"}
# Credits that are not new money coming in.
NOT_INFLOW_TREATMENTS = {"not_income", "trading_capital"}

PENALTY_RE = re.compile(r"bounce|return\s*chg|insufficient|penal|min(imum)?\s*bal|nach\s*rtn|ecs\s*rtn|dishono", re.I)
UPI_RE = re.compile(r"^upi", re.I)

DEFAULTS = {"low_balance_paise": 2_000_00, "small_ticket_paise": 200_00}

# signal key -> weight (sums to 100)
WEIGHTS = {
    "spend_vs_inflow": 25,
    "runway": 20,
    "low_balance": 12,
    "borrowing": 13,
    "trading": 12,
    "growth": 8,
    "penalties": 5,
    "cash": 5,
}


def _r(p: int) -> float:
    return round(p / 100, 2)


def _inr(p: int) -> str:
    from .tax.engine import inr

    return f"₹{inr(p / 100)}"


_HONORIFIC = re.compile(r"^(mr|mrs|ms|miss|dr|m/s)\.?\s+", re.I)


def person_key(name: str) -> str:
    """Loose grouping key for one person whose name the bank truncates differently
    ('Mr Hrishik', 'Hrishikesh Redd' -> 'hrishi')."""
    n = _HONORIFIC.sub("", name.strip()).lower()
    first = re.sub(r"[^a-z]", "", n.split(" ")[0]) if n else ""
    return first[:6] if len(first) >= 4 else ""


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _months_between(a: date, b: date) -> float:
    return max(1.0, ((b - a).days + 1) / 30.44)


def analyse(s: Session, start: date, end: date, account_id: Optional[int] = None) -> dict:
    q = (select(RawTransaction, Classification, Category)
         .join(Classification, Classification.raw_transaction_id == RawTransaction.id, isouter=True)
         .join(Category, Category.id == Classification.category_id, isouter=True)
         .where(RawTransaction.txn_date >= start, RawTransaction.txn_date <= end)
         .order_by(RawTransaction.txn_date, RawTransaction.import_batch_id, RawTransaction.row_index))
    if account_id:
        q = q.where(RawTransaction.account_id == account_id)
    rows = s.exec(q).all()

    cfg = {**DEFAULTS, **((s.get(Setting, "spend") or Setting(key="spend", value={})).value or {})}

    if not rows:
        return {"start": start.isoformat(), "end": end.isoformat(), "empty": True}

    first, last = rows[0][0].txn_date, rows[-1][0].txn_date
    months = _months_between(first, last)

    spend_total = 0
    spend_on_suggestion = 0
    uncategorised = 0
    by_cat: dict[str, dict] = defaultdict(lambda: {"amount": 0, "count": 0})
    by_payee: dict[str, dict] = defaultdict(lambda: {"amount": 0, "count": 0, "categories": defaultdict(int)})
    by_month: dict[str, int] = defaultdict(int)
    moved: dict[str, int] = defaultdict(int)
    biggest: list[dict] = []
    small_count = small_amount = 0
    cash_out = 0
    penalties = 0
    penalty_items: list[dict] = []
    inflow = 0
    loans_in = 0
    emi_out = 0
    to_broker = from_broker = 0
    credit_by_month: dict[str, int] = defaultdict(int)
    # Unconfirmed person-to-person flows, grouped loosely by name, for the two-way view.
    two_way: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "names": defaultdict(int), "n_in": 0, "n_out": 0})

    from .people import load_people, person_for

    tracked = load_people(s)
    people_flows: dict[int, dict] = {}

    for tx, c, cat in rows:
        # Tracked people have their own ledger; keep them out of spend and inflow.
        who = person_for(tx.raw_description, tracked)
        if who is not None:
            pf = people_flows.setdefault(who.id, {"id": who.id, "name": who.name, "received": 0, "sent": 0, "count": 0})
            pf["received"] += tx.credit
            pf["sent"] += tx.debit
            pf["count"] += 1
            continue
        status = c.status if c else "unclassified"
        treatment = cat.treatment if cat else None
        name = cat.name if cat else None
        cp = (c.counterparty if c else "") or ""

        # Only money nobody has explained yet: no category, or explicitly "Unexplained".
        pk = person_key(cp) if (cp and status != "confirmed" and (cat is None or treatment == "unexplained")) else ""
        if pk:
            tw = two_way[pk]
            tw["names"][cp] += tx.credit or tx.debit
            if tx.credit:
                tw["in"] += tx.credit
                tw["n_in"] += 1
            else:
                tw["out"] += tx.debit
                tw["n_out"] += 1

        if tx.credit:
            if treatment == "trading_capital":
                from_broker += tx.credit
            if name == "Loan received":
                loans_in += tx.credit
            if treatment not in NOT_INFLOW_TREATMENTS and name not in ("Refund / Reversal",):
                inflow += tx.credit
                credit_by_month[_month_key(tx.txn_date)] += tx.credit
            continue

        amt = tx.debit
        if PENALTY_RE.search(tx.raw_description):
            penalties += amt
            penalty_items.append({"date": tx.txn_date.isoformat(), "amount": amt, "narration": tx.raw_description})
        if treatment == "trading_capital":
            to_broker += amt
        if name == "EMI / Loan repayment":
            emi_out += amt

        if treatment in MOVED_TREATMENTS:
            moved[name or "Other"] += amt
            continue

        # Everything else that left the account is spend.
        label = name if (treatment in SPEND_TREATMENTS and status != "unclassified") else "Not yet categorised"
        if label == "Not yet categorised":
            uncategorised += amt
        elif status != "confirmed":
            spend_on_suggestion += amt
        spend_total += amt
        by_cat[label]["amount"] += amt
        by_cat[label]["count"] += 1
        by_month[_month_key(tx.txn_date)] += amt
        payee = cp or "(no name in narration)"
        by_payee[payee]["amount"] += amt
        by_payee[payee]["count"] += 1
        by_payee[payee]["categories"][label] += amt
        if name == "Cash withdrawal":
            cash_out += amt
        if UPI_RE.match(tx.raw_description) and amt < cfg["small_ticket_paise"]:
            small_count += 1
            small_amount += amt
        biggest.append({"id": tx.id, "date": tx.txn_date.isoformat(), "amount": amt, "category": label,
                        "payee": cp, "narration": tx.raw_description})

    # Balance behaviour: last balance of each day.
    day_bal: dict[date, int] = {}
    for tx, _, _ in rows:
        if tx.balance is not None:
            day_bal[tx.txn_date] = tx.balance
    low_days = sorted(d for d, b in day_bal.items() if b < cfg["low_balance_paise"])
    closing = next((tx.balance for tx, _, _ in reversed(rows) if tx.balance is not None), None)
    min_bal = min(day_bal.values()) if day_bal else None

    monthly_spend = spend_total / months
    month_keys = []
    d = date(first.year, first.month, 1)
    while d <= last:
        month_keys.append(_month_key(d))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    monthly = [{"month": m, "spend": by_month.get(m, 0), "inflow": credit_by_month.get(m, 0)} for m in month_keys]

    signals: list[dict] = []

    def sig(key, level, title, detail, value=None):
        signals.append({"key": key, "level": level, "title": title, "detail": detail, "value": value,
                        "weight": WEIGHTS.get(key, 0)})

    # 1. Spend vs money in
    if inflow > 0:
        ratio = spend_total / inflow
        level = "danger" if ratio > 1.0 else "watch" if ratio > 0.8 else "ok"
        sig("spend_vs_inflow", level, "Spending vs money in",
            f"You spent {_inr(spend_total)} against {_inr(inflow)} of new money in "
            f"({ratio * 100:.0f}%). " + (
                "You spent more than came in." if ratio > 1 else
                "Little is left over each month." if ratio > 0.8 else "You kept part of what came in."),
            round(ratio, 3))
    else:
        sig("spend_vs_inflow", "watch", "Spending vs money in",
            "No new money came in during this period, so every rupee spent came from savings.", None)

    # 2. Runway
    if closing is not None and monthly_spend > 0:
        runway = closing / monthly_spend
        level = "danger" if runway < 1 else "watch" if runway < 3 else "ok"
        sig("runway", level, "Cushion left",
            f"The closing balance {_inr(closing)} covers about {runway:.1f} months of spending at "
            f"{_inr(int(monthly_spend))}/month.", round(runway, 2))

    # 3. Low balance days
    total_days = max(1, len(day_bal))
    lvl = "danger" if len(low_days) >= max(10, total_days * 0.25) else "watch" if low_days else "ok"
    sig("low_balance", lvl, "Days near zero",
        f"The balance ended the day below {_inr(cfg['low_balance_paise'])} on {len(low_days)} of {total_days} days"
        + (f"; the lowest was {_inr(min_bal)}." if min_bal is not None else "."), len(low_days))

    # 4. Borrowing to fund spending
    if loans_in or emi_out:
        share = loans_in / inflow if inflow else 1
        level = "danger" if share > 0.2 else "watch"
        parts = []
        if loans_in:
            parts.append(f"{_inr(loans_in)} came in as loans ({share * 100:.0f}% of money in)")
        if emi_out:
            parts.append(f"{_inr(emi_out)} went to EMIs")
        sig("borrowing", level, "Borrowing", "; ".join(parts) + ".", round(share, 3))
    else:
        sig("borrowing", "ok", "Borrowing", "No loan disbursals or EMIs were detected.", 0)

    # 5. Trading net outflow
    net_trading = to_broker - from_broker
    if to_broker or from_broker:
        share = net_trading / inflow if inflow else (1 if net_trading > 0 else 0)
        level = "danger" if net_trading > 0 and share > 0.1 else "watch" if net_trading > 0 else "ok"
        sig("trading", level, "Money into trading",
            f"Sent {_inr(to_broker)} to brokers, got {_inr(from_broker)} back "
            + (f"(net {_inr(net_trading)} still out — held in positions or lost)." if net_trading > 0
               else "(more came back than went in)."), round(share, 3))

    # 6. Spending growth: latest full month vs the average of earlier months
    full = [m for m in monthly if m["month"] != _month_key(last) or last.day >= 28]
    if len(full) >= 3:
        recent = full[-1]["spend"]
        base = sum(m["spend"] for m in full[:-1]) / (len(full) - 1)
        if base > 0:
            g = recent / base
            level = "danger" if g > 1.6 else "watch" if g > 1.3 else "ok"
            sig("growth", level, "Spending trend",
                f"{full[-1]['month']} spending was {_inr(recent)}, {g * 100 - 100:+.0f}% vs the earlier monthly "
                f"average of {_inr(int(base))}.", round(g, 3))

    # 7. Penalties
    if penalties:
        sig("penalties", "danger", "Penalty charges",
            f"{len(penalty_items)} bounce / penalty / minimum-balance charges totalling {_inr(penalties)}.", penalties)
    else:
        sig("penalties", "ok", "Penalty charges", "No bounce or penalty charges found.", 0)

    # 8. Cash
    if spend_total:
        cs = cash_out / spend_total
        level = "watch" if cs > 0.15 else "ok"
        sig("cash", level, "Cash withdrawals",
            f"{_inr(cash_out)} withdrawn as cash ({cs * 100:.0f}% of spending). Cash spending can't be tracked.",
            round(cs, 3))

    score = 0.0
    for sg in signals:
        score += sg["weight"] * (1.0 if sg["level"] == "danger" else 0.5 if sg["level"] == "watch" else 0)
    max_w = sum(sg["weight"] for sg in signals) or 1
    score = round(score / max_w * 100)
    level = "low" if score < 25 else "moderate" if score < 50 else "high" if score < 75 else "critical"

    unc_share = uncategorised / spend_total if spend_total else 0
    notes = []
    if unc_share > 0.4:
        notes.append(f"{unc_share * 100:.0f}% of spending is not yet categorised (mostly payments to people). "
                     "Categorise it in Review for a sharper picture; it may include transfers you own.")
    if spend_on_suggestion:
        notes.append(f"{_inr(spend_on_suggestion)} of spending is based on suggested categories you haven't confirmed.")

    cats = sorted(({"category": k, **v} for k, v in by_cat.items()), key=lambda x: -x["amount"])
    for cobj in cats:
        cobj["share"] = round(cobj["amount"] / spend_total, 4) if spend_total else 0
    payees = sorted(({"payee": k, "amount": v["amount"], "count": v["count"],
                      "category": max(v["categories"].items(), key=lambda x: x[1])[0]}
                     for k, v in by_payee.items()), key=lambda x: -x["amount"])[:12]

    flows = []
    for v in two_way.values():
        if v["in"] and v["out"]:
            flows.append({"name": max(v["names"].items(), key=lambda x: x[1])[0],
                          "aliases": sorted(v["names"], key=lambda k: -v["names"][k])[:4],
                          "received": v["in"], "sent": v["out"], "net": v["in"] - v["out"],
                          "count_in": v["n_in"], "count_out": v["n_out"]})
    flows.sort(key=lambda x: -(x["received"] + x["sent"]))
    pass_through = sum(min(f["received"], f["sent"]) for f in flows)
    if pass_through and spend_total and pass_through / spend_total > 0.2:
        notes.insert(0, f"{_inr(pass_through)} of 'spending' went to people who also sent you money "
                        "(see Two-way money). If these are loans, splits or your own money moving, "
                        "categorise them in Review — real spending is likely much lower.")

    return {
        "start": start.isoformat(), "end": end.isoformat(), "empty": False,
        "two_way": flows[:10], "pass_through": pass_through,
        "people": sorted(({**v, "net": v["received"] - v["sent"]} for v in people_flows.values()),
                         key=lambda x: -(x["received"] + x["sent"])),
        "first_txn": first.isoformat(), "last_txn": last.isoformat(), "months": round(months, 2),
        "spend_total": spend_total, "monthly_avg": int(monthly_spend), "inflow": inflow,
        "uncategorised": uncategorised, "spend_on_suggestion": spend_on_suggestion,
        "closing_balance": closing, "min_balance": min_bal,
        "categories": cats,
        "payees": payees,
        "monthly": monthly,
        "moved": sorted(({"label": k, "amount": v} for k, v in moved.items()), key=lambda x: -x["amount"]),
        "biggest": sorted(biggest, key=lambda x: -x["amount"])[:10],
        "small_tickets": {"count": small_count, "amount": small_amount, "per_month": round(small_count / months, 1),
                          "under": cfg["small_ticket_paise"]},
        "risk": {"score": score, "level": level, "signals": signals},
        "penalty_items": penalty_items[:20],
        "notes": notes,
        "disclaimer": "A reading of your cash flow from bank data, not financial advice.",
    }
