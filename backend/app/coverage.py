"""Which days of each month have a statement imported, per account."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, func, select

from .models import ImportBatch, RawTransaction
from .util import fy_range


def month_coverage(s: Session, account_id: int, fy: str, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    # A statement downloaded today normally runs to yesterday.
    expected_until = today - timedelta(days=1)
    start, end = fy_range(fy)

    covered: set[date] = set()
    for b in s.exec(select(ImportBatch).where(ImportBatch.account_id == account_id,
                                              ImportBatch.period_from.is_not(None))):
        d = max(b.period_from, start)
        while d <= min(b.period_to, end):
            covered.add(d)
            d += timedelta(days=1)

    counts = dict(s.exec(
        select(func.strftime("%Y-%m", RawTransaction.txn_date), func.count(RawTransaction.id))
        .where(RawTransaction.account_id == account_id, RawTransaction.txn_date >= start, RawTransaction.txn_date <= end)
        .group_by(func.strftime("%Y-%m", RawTransaction.txn_date))).all())

    out = []
    y, m = start.year, start.month
    for _ in range(12):
        first = date(y, m, 1)
        last = date(y, m, calendar.monthrange(y, m)[1])
        key = f"{y}-{m:02d}"
        item = {"month": key, "from": first.isoformat(), "to": last.isoformat(), "txn_count": counts.get(key, 0)}
        if first > expected_until:
            item.update(status="upcoming", covered_days=0, expected_days=0, missing=[])
        else:
            upto = min(last, expected_until)
            days = [first + timedelta(days=i) for i in range((upto - first).days + 1)]
            have = [d for d in days if d in covered]
            missing = _ranges([d for d in days if d not in covered])
            status = "full" if len(have) == len(days) else "missing" if not have else "partial"
            covered_until = None
            if status == "partial":
                run = first
                while run in covered and run <= upto:
                    run += timedelta(days=1)
                covered_until = (run - timedelta(days=1)).isoformat() if run > first else None
            item.update(status=status, covered_days=len(have), expected_days=len(days), missing=missing,
                        covered_until=covered_until, in_progress=upto < last)
        out.append(item)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _ranges(days: list[date]) -> list[dict]:
    out: list[dict] = []
    for d in days:
        if out and date.fromisoformat(out[-1]["to"]) + timedelta(days=1) == d:
            out[-1]["to"] = d.isoformat()
        else:
            out.append({"from": d.isoformat(), "to": d.isoformat()})
    return out
