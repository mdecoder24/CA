"""Balance-chain reconciliation for parsed statements.

For every row: previous balance + credit - debit must equal the row balance.
If the chain breaks, try reordering rows within the same date (banks sometimes
list same-day rows out of order). If that fails, report the first bad row.
"""

from dataclasses import dataclass
from itertools import groupby
from typing import Optional

from .base import ParsedRow, ParsedStatement


@dataclass
class ReconcileResult:
    status: str  # ok | reordered | failed | totals_only | unchecked
    detail: str
    rows: list[ParsedRow]
    opening: Optional[int]
    bad_row_index: Optional[int] = None


def _fmt(p: int) -> str:
    return f"₹{p / 100:,.2f}"


def _chain_break(rows: list[ParsedRow], opening: int) -> Optional[int]:
    bal = opening
    for i, r in enumerate(rows):
        bal = bal + r.credit - r.debit
        if r.balance is not None and r.balance != bal:
            return i
        if r.balance is not None:
            bal = r.balance
    return None


def _reorder_same_day(rows: list[ParsedRow], opening: int) -> Optional[list[ParsedRow]]:
    """Greedy: within each date, pick the next row whose balance continues the chain."""
    out: list[ParsedRow] = []
    bal = opening
    for _, grp in groupby(rows, key=lambda r: r.txn_date):
        pending = list(grp)
        while pending:
            pick = None
            for r in pending:
                if r.balance is None or r.balance == bal + r.credit - r.debit:
                    pick = r
                    break
            if pick is None:
                return None
            pending.remove(pick)
            out.append(pick)
            bal = pick.balance if pick.balance is not None else bal + pick.credit - pick.debit
    return out


def reconcile(st: ParsedStatement) -> ReconcileResult:
    rows = st.rows
    has_balances = sum(1 for r in rows if r.balance is not None) >= max(1, len(rows) // 2)

    if not has_balances:
        if st.opening_balance is not None and st.closing_balance is not None:
            net = sum(r.credit - r.debit for r in rows)
            if st.opening_balance + net == st.closing_balance:
                return ReconcileResult("totals_only", "No running balance column; opening + net = closing matches.",
                                       rows, st.opening_balance)
            return ReconcileResult(
                "failed",
                f"Opening {_fmt(st.opening_balance)} + net {_fmt(net)} ≠ closing {_fmt(st.closing_balance)}.",
                rows, st.opening_balance)
        return ReconcileResult("unchecked", "No running balance and no opening/closing balance found; cannot verify.",
                               rows, st.opening_balance)

    opening = st.opening_balance
    if opening is None:
        first = rows[0]
        opening = (first.balance or 0) - first.credit + first.debit

    bad = _chain_break(rows, opening)
    if bad is None:
        detail = "Balance chain reconciles for every row."
        if st.closing_balance is not None and rows[-1].balance is not None and rows[-1].balance != st.closing_balance:
            return ReconcileResult("failed", f"Last row balance {_fmt(rows[-1].balance)} ≠ statement closing "
                                             f"{_fmt(st.closing_balance)}.", rows, opening, len(rows) - 1)
        return ReconcileResult("ok", detail, rows, opening)

    reordered = _reorder_same_day(rows, opening)
    if reordered is not None and _chain_break(reordered, opening) is None:
        return ReconcileResult("reordered", "Same-day rows were reordered to make the balance chain reconcile.",
                               reordered, opening)

    r = rows[bad]
    prev = rows[bad - 1].balance if bad > 0 and rows[bad - 1].balance is not None else opening
    expected = (prev or 0) + r.credit - r.debit
    return ReconcileResult(
        "failed",
        f"Row {bad + 1} ({r.txn_date:%d-%m-%Y}, “{r.description[:60]}”): expected balance {_fmt(expected)}, "
        f"statement shows {_fmt(r.balance or 0)}. A row may be missing or misread.",
        rows, opening, bad)
