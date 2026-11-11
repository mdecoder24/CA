"""Statement import: store file, parse, reconcile, dedupe, insert, classify, flag."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from .anomalies import run_flags
from .classify import apply_rules
from .db import data_dir
from .importers.base import ParsedStatement
from .importers.reconcile import reconcile
from .models import Account, ImportBatch, RawTransaction
from .transfers import match_own_transfers
from .util import audit

from .banks import bank_name, get_parser
ALLOWED = {"csv", "xls", "xlsx", "pdf"}


class ImportRejected(Exception):
    def __init__(self, message: str, code: str = "rejected", detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def fingerprint(account_id: int, r) -> str:
    # Balance makes each row unique; without it fall back to narration.
    tail = str(r.balance) if r.balance is not None else r.description
    raw = f"{account_id}|{r.txn_date.isoformat()}|{r.debit}|{r.credit}|{r.ref_no}|{tail}"
    return hashlib.sha256(raw.encode()).hexdigest()


def recheck_batch(s: Session, batch_id: int, password: Optional[str] = None) -> ImportBatch:
    """Re-parse a stored statement and re-run reconciliation (e.g. after a parser fix).

    Only the batch's check result changes. Imported rows are never modified.
    """
    batch = s.get(ImportBatch, batch_id)
    if batch is None:
        raise ImportRejected("Unknown import.")
    account = s.get(Account, batch.account_id)
    st = get_parser(account.bank).parse(Path(batch.stored_path), batch.file_type, password=password)
    rec = reconcile(st)
    before = {"status": batch.status, "reconcile_detail": batch.reconcile_detail,
              "closing_balance": batch.closing_balance, "override_reason": batch.override_reason}
    if rec.status != "failed":
        batch.status = {"ok": "ok", "reordered": "reordered", "totals_only": "ok", "unchecked": "unchecked"}[rec.status]
        if before["override_reason"]:
            # Keep the old reason visible in the audit log; the override is no longer needed.
            batch.override_reason = ""
    batch.reconcile_detail = rec.detail
    p_from, p_to = st.period
    if p_from and p_to:
        batch.period_from, batch.period_to = p_from, p_to
    if st.closing_balance is not None:
        batch.closing_balance = st.closing_balance
    s.add(batch)
    audit(s, "import_batch", batch.id, "recheck", before=before,
          after={"status": batch.status, "reconcile_detail": batch.reconcile_detail,
                 "closing_balance": batch.closing_balance, "override_reason": batch.override_reason})
    s.commit()
    s.refresh(batch)
    return batch


def continuity(s: Session, account_id: int, first_date, opening: Optional[int], exclude_batch: Optional[int] = None) -> dict:
    """Does this statement's opening balance continue from the last stored balance before it?"""
    if opening is None or first_date is None:
        return {"ok": True, "checked": False, "message": "Opening balance not found; continuity not checked."}
    q = (select(RawTransaction).where(RawTransaction.account_id == account_id, RawTransaction.txn_date < first_date,
                                      RawTransaction.balance.is_not(None))
         .order_by(RawTransaction.txn_date.desc(), RawTransaction.import_batch_id.desc(), RawTransaction.row_index.desc()))
    if exclude_batch is not None:
        q = q.where(RawTransaction.import_batch_id != exclude_batch)
    prev = s.exec(q).first()
    if prev is None:
        return {"ok": True, "checked": False, "message": "First statement for this account."}
    if prev.balance == opening:
        return {"ok": True, "checked": True, "message": f"Continues exactly from {prev.txn_date:%d-%m-%Y}."}
    return {"ok": False, "checked": True,
            "message": (f"Opening balance ₹{opening / 100:,.2f} does not match the stored balance ₹{prev.balance / 100:,.2f} "
                        f"on {prev.txn_date:%d-%m-%Y}. Transactions between the two statements may be missing — "
                        "import the statement that covers that gap.")}


@dataclass
class ImportOutcome:
    batch: ImportBatch
    inserted: int
    duplicates: int
    continuity: dict


def import_statement(s: Session, account_id: int, filename: str, tmp_path: Path,
                     password: Optional[str] = None, override_reason: str = "",
                     force_account: bool = False) -> ImportOutcome:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED:
        raise ImportRejected(f"Unsupported file type .{ext}. Use CSV, XLS, XLSX or PDF.")
    account = s.get(Account, account_id)
    if account is None:
        raise ImportRejected("Unknown account.")

    sha = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
    prior = s.exec(select(ImportBatch).where(ImportBatch.sha256 == sha)).first()
    if prior:
        raise ImportRejected(f"This exact file was already imported on {prior.created_at:%d %b %Y} "
                             f"as “{prior.filename}”.", code="duplicate_file")

    parser = get_parser(account.bank)
    # Password is used in memory only and never stored or logged.
    st: ParsedStatement = parser.parse(tmp_path, ext, password=password)
    rec = reconcile(st)

    # Guard against uploading one bank's statement into another account.
    stmt4 = re.sub(r"\D", "", st.masked_account)[-4:]
    acct4 = re.sub(r"\D", "", account.masked_number or "")[-4:]
    if stmt4 and acct4 and stmt4 != acct4 and not force_account:
        raise ImportRejected(
            f"This statement is for account ending {stmt4}, but you chose {bank_name(account.bank)} ending {acct4}. "
            "Pick the right account, or add this one under Accounts.", code="account_mismatch")

    if rec.status == "failed" and not override_reason.strip():
        raise ImportRejected(rec.detail, code="reconcile_failed",
                             detail={"bad_row": rec.bad_row_index, "rows": len(rec.rows)})

    status = {"ok": "ok", "reordered": "reordered", "totals_only": "ok", "unchecked": "unchecked",
              "failed": "override"}[rec.status]

    dest_dir = data_dir() / "uploads"
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(filename).name)[-80:]
    dest = dest_dir / f"{sha[:12]}_{safe_name}"
    shutil.copyfile(tmp_path, dest)

    p_from, p_to = st.period
    first_row_date = rec.rows[0].txn_date if rec.rows else p_from
    cont = continuity(s, account_id, first_row_date, rec.opening)
    batch = ImportBatch(account_id=account_id, filename=Path(filename).name[:200], sha256=sha, stored_path=str(dest),
                        file_type=ext, period_from=p_from, period_to=p_to, opening_balance=rec.opening,
                        closing_balance=st.closing_balance if st.closing_balance is not None else
                        (rec.rows[-1].balance if rec.rows else None),
                        rows_parsed=len(rec.rows), status=status, reconcile_detail=rec.detail,
                        override_reason=override_reason.strip() if rec.status == "failed" else "")
    if not cont["ok"]:
        batch.reconcile_detail = f"{rec.detail} Continuity: {cont['message']}"
    s.add(batch)
    s.flush()

    if st.masked_account and not account.masked_number:
        account.masked_number = st.masked_account
        s.add(account)

    existing = set(s.exec(select(RawTransaction.fingerprint).where(RawTransaction.account_id == account_id)).all())
    new_txs: list[RawTransaction] = []
    dupes = 0
    seen_in_file: dict[str, int] = {}
    for i, r in enumerate(rec.rows):
        fp = fingerprint(account_id, r)
        if fp in existing:
            dupes += 1
            continue
        # Two genuinely identical rows inside one file (no balance column): keep both.
        if fp in seen_in_file:
            seen_in_file[fp] += 1
            fp = f"{fp}:{seen_in_file[fp]}"
        else:
            seen_in_file[fp] = 0
        tx = RawTransaction(account_id=account_id, import_batch_id=batch.id, row_index=i, txn_date=r.txn_date,
                            value_date=r.value_date, raw_description=r.description, ref_no=r.ref_no,
                            debit=r.debit, credit=r.credit, balance=r.balance, fingerprint=fp)
        s.add(tx)
        new_txs.append(tx)
    batch.rows_inserted, batch.rows_duplicate = len(new_txs), dupes
    s.add(batch)
    s.flush()
    audit(s, "import_batch", batch.id, "create", after={"filename": batch.filename, "status": status,
                                                         "inserted": len(new_txs), "duplicates": dupes,
                                                         "override_reason": batch.override_reason})
    s.commit()

    apply_rules(s, new_txs, account.profile_id)
    match_own_transfers(s, account.profile_id)
    run_flags(s)
    s.refresh(batch)
    return ImportOutcome(batch=batch, inserted=len(new_txs), duplicates=dupes, continuity=cont)
