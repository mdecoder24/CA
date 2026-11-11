"""Tracked people: separate ledgers for people money goes back and forth with.

A person is matched by a case-insensitive regular expression against the
original bank narration (e.g. ``exampl`` matches "Mr Exampl",
"Example Redd" and "SentIMPS…Example/…"). The first matching person
wins, in creation order. Raw transactions are never modified.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from .models import Category, Classification, Person, RawTransaction


def compile_pattern(pattern: str) -> re.Pattern:
    p = pattern.strip()
    if not p:
        raise ValueError("Match text is required")
    if len(p) > 200:
        raise ValueError("Match text is too long")
    try:
        return re.compile(p, re.I)
    except re.error as e:
        raise ValueError(f"Invalid match text: {e}") from e


def load_people(s: Session, profile_id: int = 1) -> list[tuple[Person, re.Pattern]]:
    out = []
    for p in s.exec(select(Person).where(Person.profile_id == profile_id).order_by(Person.id)):
        try:
            out.append((p, compile_pattern(p.pattern)))
        except ValueError:
            continue
    return out


def person_for(text: str, people: list[tuple[Person, re.Pattern]]) -> Optional[Person]:
    for p, rx in people:
        if rx.search(text):
            return p
    return None


def _rows(s: Session, start: date, end: date, account_id: Optional[int] = None):
    q = (
        select(RawTransaction, Classification, Category)
        .join(Classification, Classification.raw_transaction_id == RawTransaction.id, isouter=True)
        .join(Category, Category.id == Classification.category_id, isouter=True)
        .where(RawTransaction.txn_date >= start, RawTransaction.txn_date <= end)
        .order_by(RawTransaction.txn_date, RawTransaction.import_batch_id, RawTransaction.row_index))
    if account_id:
        q = q.where(RawTransaction.account_id == account_id)
    return s.exec(q).all()


def summaries(s: Session, start: date, end: date, account_id: Optional[int] = None) -> list[dict]:
    people = load_people(s)
    tot: dict[int, dict] = {p.id: {"received": 0, "sent": 0, "count": 0, "last": None} for p, _ in people}
    for tx, _, _ in _rows(s, start, end, account_id):
        p = person_for(tx.raw_description, people)
        if p is None:
            continue
        t = tot[p.id]
        t["received"] += tx.credit
        t["sent"] += tx.debit
        t["count"] += 1
        t["last"] = tx.txn_date.isoformat()
    return [{"id": p.id, "name": p.name, "pattern": p.pattern, "pinned": p.pinned, "note": p.note,
             **tot[p.id], "net": tot[p.id]["received"] - tot[p.id]["sent"]} for p, _ in people]


def ledger(s: Session, person: Person, start: date, end: date, account_id: Optional[int] = None) -> dict:
    people = load_people(s)
    rows = []
    running = 0
    monthly: dict[str, dict] = defaultdict(lambda: {"received": 0, "sent": 0})
    by_cat: dict[str, dict] = defaultdict(lambda: {"received": 0, "sent": 0, "count": 0})
    names: dict[str, int] = defaultdict(int)
    for tx, c, cat in _rows(s, start, end, account_id):
        who = person_for(tx.raw_description, people)
        if who is None or who.id != person.id:
            continue
        running += tx.credit - tx.debit
        key = f"{tx.txn_date.year}-{tx.txn_date.month:02d}"
        monthly[key]["received"] += tx.credit
        monthly[key]["sent"] += tx.debit
        label = cat.name if cat else "Not yet categorised"
        by_cat[label]["received"] += tx.credit
        by_cat[label]["sent"] += tx.debit
        by_cat[label]["count"] += 1
        if c and c.counterparty:
            names[c.counterparty] += 1
        rows.append({
            "id": tx.id, "date": tx.txn_date.isoformat(), "narration": tx.raw_description, "ref_no": tx.ref_no,
            "received": tx.credit, "sent": tx.debit, "running_net": running,
            "direction": "credit" if tx.credit else "debit",
            "category_id": c.category_id if c else None, "category": cat.name if cat else None,
            "status": c.status if c else "unclassified", "note": c.note if c else "",
        })
    received = sum(r["received"] for r in rows)
    sent = sum(r["sent"] for r in rows)
    month_list = [{"month": k, **v} for k, v in sorted(monthly.items())]
    return {
        "person": {"id": person.id, "name": person.name, "pattern": person.pattern, "pinned": person.pinned,
                   "note": person.note},
        "start": start.isoformat(), "end": end.isoformat(),
        "received": received, "sent": sent, "net": received - sent,
        "count": len(rows), "count_in": sum(1 for r in rows if r["received"]),
        "count_out": sum(1 for r in rows if r["sent"]),
        "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
        "largest_in": max((r["received"] for r in rows), default=0),
        "largest_out": max((r["sent"] for r in rows), default=0),
        "monthly": month_list,
        "by_category": sorted(({"category": k, **v} for k, v in by_cat.items()),
                              key=lambda x: -(x["received"] + x["sent"])),
        "names_seen": sorted(names, key=lambda k: -names[k])[:8],
        "unconfirmed": sum(1 for r in rows if r["status"] != "confirmed"),
        "rows": rows,
    }


def suggestions(s: Session, start: date, end: date, limit: int = 8, account_id: Optional[int] = None) -> list[dict]:
    """People not yet tracked whom money went both to and from, largest first."""
    from .spend import person_key

    people = load_people(s)
    groups: dict[str, dict] = defaultdict(lambda: {"received": 0, "sent": 0, "count": 0, "names": defaultdict(int)})
    for tx, c, cat in _rows(s, start, end, account_id):
        if person_for(tx.raw_description, people) is not None:
            continue
        if cat is not None and cat.treatment in ("not_income", "trading_capital", "salary"):
            continue
        cp = c.counterparty if c else ""
        k = person_key(cp) if cp else ""
        if not k:
            continue
        g = groups[k]
        g["received"] += tx.credit
        g["sent"] += tx.debit
        g["count"] += 1
        g["names"][cp] += 1
    out = []
    for k, g in groups.items():
        if g["received"] and g["sent"] and g["count"] >= 3:
            name = max(g["names"].items(), key=lambda x: x[1])[0]
            out.append({"key": k, "name": name, "pattern": re.escape(k), "received": g["received"], "sent": g["sent"],
                        "count": g["count"], "names_seen": sorted(g["names"], key=lambda n: -g["names"][n])[:4]})
    out.sort(key=lambda x: -(x["received"] + x["sent"]))
    return out[:limit]
