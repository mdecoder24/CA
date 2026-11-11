"""Match transfers between the owner's own accounts.

A debit in one account and a credit of the same amount in another account
within a few days is almost always money moving between your own accounts.
Both sides are suggested as "Transfer – own account" (never auto-confirmed)
so "All accounts" totals don't count the same money twice.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlmodel import Session, select

from .banks import bank_name
from .classify import extract_counterparty
from .models import Account, Category, Classification, ClassificationHistory, RawTransaction, now

WINDOW_DAYS = 3


def match_own_transfers(s: Session, profile_id: int = 1) -> int:
    accounts = {a.id: a for a in s.exec(select(Account).where(Account.profile_id == profile_id))}
    if len(accounts) < 2:
        return 0
    cats = {(c.name, c.direction): c.id for c in s.exec(select(Category).where(Category.profile_id == profile_id))}
    cat_in = cats.get(("Transfer – own account", "credit"))
    cat_out = cats.get(("Transfer – own account", "debit"))
    if not (cat_in and cat_out):
        return 0

    rows = s.exec(select(RawTransaction, Classification)
                  .join(Classification, Classification.raw_transaction_id == RawTransaction.id, isouter=True)
                  .where(RawTransaction.account_id.in_(list(accounts)))
                  .order_by(RawTransaction.txn_date, RawTransaction.id)).all()

    def free(c: Classification | None) -> bool:
        return c is None or c.status != "confirmed" and c.source not in ("user", "match")

    credits_by_amount: dict[int, list] = defaultdict(list)
    for tx, c in rows:
        if tx.credit and free(c):
            credits_by_amount[tx.credit].append((tx, c))

    used: set[int] = set()
    matched = 0
    for tx, c in rows:
        if not tx.debit or not free(c) or tx.id in used:
            continue
        for ctx, cc in credits_by_amount.get(tx.debit, []):
            if ctx.id in used or ctx.account_id == tx.account_id:
                continue
            if abs((ctx.txn_date - tx.txn_date).days) > WINDOW_DAYS:
                continue
            a_out, a_in = accounts[tx.account_id], accounts[ctx.account_id]
            _set(s, tx, c, cat_out, f"Matched: arrived in {_label(a_in)} on {ctx.txn_date:%d-%m-%Y}")
            _set(s, ctx, cc, cat_in, f"Matched: sent from {_label(a_out)} on {tx.txn_date:%d-%m-%Y}")
            used.update({tx.id, ctx.id})
            matched += 1
            break
    s.commit()
    return matched


def _label(a: Account) -> str:
    return f"{bank_name(a.bank)} {a.masked_number}".strip() if a.masked_number else (a.nickname or bank_name(a.bank))


def _set(s: Session, tx: RawTransaction, c: Classification | None, category_id: int, note: str) -> None:
    if c is None:
        c = Classification(raw_transaction_id=tx.id, counterparty=extract_counterparty(tx.raw_description))
    c.category_id, c.status, c.source, c.confidence, c.updated_at = category_id, "suggested", "match", 0.9, now()
    if not c.note:
        c.note = note
    s.add(c)
    s.flush()
    s.add(ClassificationHistory(raw_transaction_id=tx.id, category_id=category_id, status="suggested",
                                source="match", note=note))
