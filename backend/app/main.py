"""FinTrack API. Binds to 127.0.0.1 only (see dev.sh). No auth: localhost single user."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from sqlmodel import Session, func, select

from . import reports
from .anomalies import run_flags
from .classify import apply_rules, extract_counterparty, llm_suggest, set_classification
from .db import data_dir, get_session, init_db
from .importers.base import PasswordRequired, StatementError
from .ingest import ImportRejected, import_statement, recheck_batch
from .models import (Account, AuditLog, Category, Classification, Flag, ImportBatch, RawTransaction, Rule, Setting,
                     TaxInput)
from .spend import analyse as spend_analyse
from .summary import dashboard, fy_rows, tax_estimate
from .tax import engine
from .util import audit, fy_of, fy_range

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="FinTrack", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def require_app_header(request: Request, call_next):
    # Mutating requests must carry a custom header. Browsers cannot add it cross-site
    # without a CORS preflight, which our CORS policy rejects for other origins (CSRF guard).
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-fintrack") != "1":
        return JSONResponse({"detail": "Missing X-FinTrack header"}, status_code=403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("FINTRACK_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


# ---------------------------------------------------------------- meta
@app.get("/api/meta")
def meta(s: Session = Depends(get_session)):
    years = {fy_of(d) for d in s.exec(select(RawTransaction.txn_date)).all()}
    years |= set(engine.available_fys())
    current = fy_of(date.today())
    return {"fys": sorted(years, reverse=True), "current_fy": current,
            "default_fy": max((y for y in years if s.exec(select(func.count(RawTransaction.id)).where(
                RawTransaction.txn_date >= fy_range(y)[0], RawTransaction.txn_date <= fy_range(y)[1])).one()),
                default=current),
            "accounts": s.exec(select(Account)).all(), "data_dir": str(data_dir())}


@app.get("/api/dashboard")
def get_dashboard(fy: str, s: Session = Depends(get_session)):
    return dashboard(s, fy)


# ---------------------------------------------------------------- imports
@app.get("/api/imports")
def list_imports(s: Session = Depends(get_session)):
    return s.exec(select(ImportBatch).order_by(ImportBatch.created_at.desc())).all()


@app.post("/api/imports")
async def upload(file: UploadFile = File(...), account_id: int = Form(1), password: str = Form(""),
                 override_reason: str = Form(""), s: Session = Depends(get_session)):
    suffix = Path(file.filename or "statement").suffix.lower()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / f"upload{suffix}"
        size = 0
        with tmp.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File is larger than 25 MB.")
                out.write(chunk)
        try:
            res = import_statement(s, account_id, file.filename or f"statement{suffix}", tmp,
                                   password=password or None, override_reason=override_reason)
        except PasswordRequired as e:
            raise HTTPException(422, {"code": "password_required", "message": str(e)})
        except ImportRejected as e:
            raise HTTPException(422, {"code": e.code, "message": str(e), **e.detail})
        except StatementError as e:
            raise HTTPException(422, {"code": "parse_error", "message": str(e)})
    return {"batch": res.batch, "inserted": res.inserted, "duplicates": res.duplicates}


@app.post("/api/imports/{batch_id}/recheck")
def recheck_import(batch_id: int, password: str = Form(""), s: Session = Depends(get_session)):
    try:
        return recheck_batch(s, batch_id, password=password or None)
    except PasswordRequired as e:
        raise HTTPException(422, {"code": "password_required", "message": str(e)})
    except (ImportRejected, StatementError) as e:
        raise HTTPException(422, {"code": "recheck_failed", "message": str(e)})


# ---------------------------------------------------------------- transactions
def _tx_out(tx: RawTransaction, c: Optional[Classification], cat: Optional[Category], flags: list[Flag]):
    return {
        "id": tx.id, "txn_date": tx.txn_date, "value_date": tx.value_date, "raw_description": tx.raw_description,
        "ref_no": tx.ref_no, "debit": tx.debit, "credit": tx.credit, "balance": tx.balance,
        "direction": "credit" if tx.credit else "debit",
        "category_id": c.category_id if c else None, "category": cat.name if cat else None,
        "treatment": cat.treatment if cat else None,
        "status": c.status if c else "unclassified", "source": c.source if c else "none",
        "confidence": c.confidence if c else None, "note": c.note if c else "", "nature": c.nature if c else "personal",
        "counterparty": (c.counterparty if c else "") or extract_counterparty(tx.raw_description),
        "flags": [{"id": f.id, "type": f.type, "detail": f.detail, "resolved": f.resolved,
                   "resolution_note": f.resolution_note} for f in flags],
    }


def _flags_by_tx(s: Session) -> dict[int, list[Flag]]:
    out: dict[int, list[Flag]] = {}
    for f in s.exec(select(Flag)):
        out.setdefault(f.raw_transaction_id, []).append(f)
    return out


@app.get("/api/transactions")
def list_transactions(fy: str, direction: Optional[str] = None, status: Optional[str] = None,
                      category_id: Optional[int] = None, q: Optional[str] = None, month: Optional[str] = None,
                      flagged: bool = False, s: Session = Depends(get_session)):
    flags = _flags_by_tx(s)
    out = []
    for tx, c, cat in fy_rows(s, fy):
        d = "credit" if tx.credit else "debit"
        st = c.status if c else "unclassified"
        if direction and d != direction:
            continue
        if status == "unconfirmed" and st == "confirmed":
            continue
        if status and status != "unconfirmed" and st != status:
            continue
        if category_id and (not c or c.category_id != category_id):
            continue
        if month and f"{tx.txn_date:%Y-%m}" != month:
            continue
        open_flags = [f for f in flags.get(tx.id, []) if not f.resolved]
        if flagged and not open_flags:
            continue
        if q:
            ql = q.lower()
            if ql not in tx.raw_description.lower() and ql not in (c.note.lower() if c else "") \
                    and ql not in tx.ref_no.lower():
                continue
        out.append(_tx_out(tx, c, cat, flags.get(tx.id, [])))
    return out


@app.get("/api/review")
def review_queue(fy: str, direction: str = "credit", s: Session = Depends(get_session)):
    flags = _flags_by_tx(s)
    items = []
    for tx, c, cat in fy_rows(s, fy):
        d = "credit" if tx.credit else "debit"
        if d != direction:
            continue
        open_flags = [f for f in flags.get(tx.id, []) if not f.resolved]
        unexplained = cat is not None and cat.treatment == "unexplained"
        if (c and c.status == "confirmed") and not open_flags and not unexplained:
            continue
        items.append(_tx_out(tx, c, cat, flags.get(tx.id, [])))
    items.sort(key=lambda x: (0 if any(not f["resolved"] for f in x["flags"]) else 1,
                              0 if x["status"] == "suggested" else 1, -(x["credit"] or x["debit"])))
    return items


class ClassifyIn(BaseModel):
    category_id: Optional[int] = None
    note: Optional[str] = None
    nature: Optional[str] = None
    confirm: bool = True
    make_rule: bool = False
    rule_pattern: Optional[str] = None


@app.patch("/api/transactions/{tx_id}/classification")
def classify_tx(tx_id: int, body: ClassifyIn, s: Session = Depends(get_session)):
    tx = s.get(RawTransaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    if body.category_id is not None:
        cat = s.get(Category, body.category_id)
        direction = "credit" if tx.credit else "debit"
        if cat is None or cat.direction != direction:
            raise HTTPException(400, f"Category must be a {direction} category.")
    before = s.exec(select(Classification).where(Classification.raw_transaction_id == tx_id)).first()
    before_d = before.model_dump() if before else None
    c = set_classification(s, tx_id, body.category_id, body.note, body.nature, body.confirm)
    audit(s, "classification", tx_id, "update", before=before_d, after=c)
    rule_id = None
    if body.make_rule and c.category_id:
        pattern = (body.rule_pattern or c.counterparty or "").strip()
        if pattern:
            r = Rule(profile_id=1, priority=5, match_type="contains", pattern=pattern,
                     direction="credit" if tx.credit else "debit", category_id=c.category_id, auto_confirm=False)
            s.add(r)
            s.flush()
            audit(s, "rule", r.id, "create", after=r)
            rule_id = r.id
    s.commit()
    if rule_id:
        apply_rules(s, s.exec(select(RawTransaction)).all(), 1)
    run_flags(s)
    return {"ok": True, "rule_id": rule_id}


class BulkIn(BaseModel):
    ids: list[int]
    category_id: Optional[int] = None
    confirm: bool = True


@app.post("/api/transactions/bulk-classify")
def bulk_classify(body: BulkIn, s: Session = Depends(get_session)):
    n = 0
    for tx_id in body.ids:
        tx = s.get(RawTransaction, tx_id)
        if tx is None:
            continue
        if body.category_id is not None:
            cat = s.get(Category, body.category_id)
            if cat is None or cat.direction != ("credit" if tx.credit else "debit"):
                continue
        c = set_classification(s, tx_id, body.category_id, None, None, body.confirm)
        audit(s, "classification", tx_id, "bulk_update", after=c)
        n += 1
    s.commit()
    run_flags(s)
    return {"updated": n}


class FlagIn(BaseModel):
    resolved: bool
    resolution_note: str = ""


@app.patch("/api/flags/{flag_id}")
def resolve_flag(flag_id: int, body: FlagIn, s: Session = Depends(get_session)):
    f = s.get(Flag, flag_id)
    if f is None:
        raise HTTPException(404, "Flag not found")
    before = f.model_dump()
    f.resolved, f.resolution_note = body.resolved, body.resolution_note
    s.add(f)
    audit(s, "flag", f.id, "update", before=before, after=f)
    s.commit()
    return f


# ---------------------------------------------------------------- categories & rules
@app.get("/api/categories")
def list_categories(s: Session = Depends(get_session)):
    return s.exec(select(Category).order_by(Category.direction, Category.sort)).all()


class CategoryIn(BaseModel):
    name: str
    direction: str
    treatment: str


@app.post("/api/categories")
def create_category(body: CategoryIn, s: Session = Depends(get_session)):
    if body.direction not in ("credit", "debit") or body.treatment not in engine.TREATMENTS:
        raise HTTPException(400, "Invalid direction or treatment")
    c = Category(profile_id=1, name=body.name.strip()[:80], direction=body.direction, treatment=body.treatment,
                 sort=1000)
    s.add(c)
    s.flush()
    audit(s, "category", c.id, "create", after=c)
    s.commit()
    s.refresh(c)
    return c


@app.get("/api/rules")
def list_rules(s: Session = Depends(get_session)):
    return s.exec(select(Rule).order_by(Rule.priority, Rule.id)).all()


class RuleIn(BaseModel):
    pattern: str
    match_type: str = "contains"
    direction: str = "any"
    category_id: int
    priority: int = 100
    auto_confirm: bool = False
    enabled: bool = True
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None


def _check_rule(body: RuleIn, s: Session):
    import re

    if body.match_type not in ("contains", "regex", "exact") or body.direction not in ("credit", "debit", "any"):
        raise HTTPException(400, "Invalid match type or direction")
    if not body.pattern.strip():
        raise HTTPException(400, "Pattern is required")
    if body.match_type == "regex":
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(400, f"Invalid regex: {e}")
    if s.get(Category, body.category_id) is None:
        raise HTTPException(400, "Unknown category")


@app.post("/api/rules")
def create_rule(body: RuleIn, s: Session = Depends(get_session)):
    _check_rule(body, s)
    r = Rule(profile_id=1, **body.model_dump())
    s.add(r)
    s.flush()
    audit(s, "rule", r.id, "create", after=r)
    s.commit()
    s.refresh(r)
    return r


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, s: Session = Depends(get_session)):
    r = s.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found")
    _check_rule(body, s)
    before = r.model_dump()
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    s.add(r)
    audit(s, "rule", r.id, "update", before=before, after=r)
    s.commit()
    s.refresh(r)
    return r


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, s: Session = Depends(get_session)):
    r = s.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found")
    audit(s, "rule", r.id, "delete", before=r)
    s.delete(r)
    s.commit()
    return {"ok": True}


@app.post("/api/rules/rerun")
def rerun_rules(s: Session = Depends(get_session)):
    n = apply_rules(s, s.exec(select(RawTransaction)).all(), 1)
    run_flags(s)
    return {"changed": n}


@app.post("/api/ai/suggest")
def ai_suggest(s: Session = Depends(get_session)):
    res = llm_suggest(s, 1)
    run_flags(s)
    return res


# ---------------------------------------------------------------- spend
@app.get("/api/spend")
def spend(fy: Optional[str] = None, start: Optional[date] = None, end: Optional[date] = None,
          batch_id: Optional[int] = None, s: Session = Depends(get_session)):
    """Spend analytics for an FY, an explicit date range, or one imported statement's period."""
    if batch_id is not None:
        b = s.get(ImportBatch, batch_id)
        if b is None or b.period_from is None:
            raise HTTPException(404, "Import not found")
        start, end = b.period_from, b.period_to
    elif fy:
        start, end = fy_range(fy)
    if start is None or end is None or start > end:
        raise HTTPException(400, "Give fy, batch_id, or start and end dates")
    return spend_analyse(s, start, end)


# ---------------------------------------------------------------- tax
@app.get("/api/tax/{fy}")
def get_tax(fy: str, s: Session = Depends(get_session)):
    if fy not in engine.available_fys():
        raise HTTPException(404, f"No tax rules for FY {fy}. Available: {', '.join(engine.available_fys())}")
    ti = s.exec(select(TaxInput).where(TaxInput.profile_id == 1, TaxInput.fy == fy)).first()
    return {"inputs": engine.merge_inputs(ti.data if ti else {}), "estimate": tax_estimate(s, fy)}


@app.put("/api/tax/{fy}/inputs")
def put_tax_inputs(fy: str, body: dict, s: Session = Depends(get_session)):
    if fy not in engine.available_fys():
        raise HTTPException(404, "Unknown FY")
    clean = engine.merge_inputs({k: v for k, v in body.items() if k in engine.DEFAULT_INPUTS})
    ti = s.exec(select(TaxInput).where(TaxInput.profile_id == 1, TaxInput.fy == fy)).first()
    before = dict(ti.data) if ti else None
    if ti is None:
        ti = TaxInput(profile_id=1, fy=fy, data=clean)
    else:
        ti.data = clean
    s.add(ti)
    s.flush()
    audit(s, "tax_input", ti.id, "update", before=before, after=clean)
    s.commit()
    return {"inputs": clean, "estimate": tax_estimate(s, fy)}


# ---------------------------------------------------------------- reports
@app.post("/api/reports/{fy}/{kind}")
def make_report(fy: str, kind: str, s: Session = Depends(get_session)):
    if fy not in engine.available_fys():
        raise HTTPException(404, "Unknown FY")
    if kind == "excel":
        path = reports.build_excel(s, fy)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif kind == "pdf":
        path = reports.build_pdf(s, fy)
        media = "application/pdf"
    else:
        raise HTTPException(400, "kind must be excel or pdf")
    return FileResponse(path, media_type=media, filename=path.name)


# ---------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings(s: Session = Depends(get_session)):
    return {st.key: st.value for st in s.exec(select(Setting))}


@app.put("/api/settings/{key}")
def put_setting(key: str, body: dict, s: Session = Depends(get_session)):
    st = s.get(Setting, key)
    if st is None:
        raise HTTPException(404, "Unknown setting")
    before = dict(st.value)
    if key == "ollama":
        from urllib.parse import urlparse

        u = urlparse(str(body.get("url", st.value.get("url", ""))))
        if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost") or u.username or u.password:
            raise HTTPException(400, "Ollama URL must be on this machine (127.0.0.1 or localhost).")
    st.value = {**st.value, **body}
    s.add(st)
    audit(s, "setting", 0, f"update:{key}", before=before, after=st.value)
    s.commit()
    if key == "anomaly":
        run_flags(s)
    return st.value


class BackupIn(BaseModel):
    folder: Optional[str] = None


@app.post("/api/backup")
def backup(body: BackupIn):
    src = data_dir()
    dest_root = Path(body.folder).expanduser() if body.folder else src / "backups"
    dest = dest_root / f"fintrack-backup-{datetime.now():%Y%m%d-%H%M%S}"
    dest.mkdir(parents=True, exist_ok=False)
    import sqlite3

    # Online backup API gives a consistent copy even while the app is running.
    with sqlite3.connect(src / "fintrack.db") as srcdb, sqlite3.connect(dest / "fintrack.db") as dst:
        srcdb.backup(dst)
    if (src / "uploads").exists():
        shutil.copytree(src / "uploads", dest / "uploads")
    return {"path": str(dest)}


@app.get("/api/audit")
def audit_log(limit: int = 200, s: Session = Depends(get_session)):
    return s.exec(select(AuditLog).order_by(AuditLog.at.desc()).limit(min(limit, 1000))).all()
