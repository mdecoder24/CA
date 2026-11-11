"""Classification pipeline: rules -> optional local LLM (Ollama) -> review queue.

Never touches RawTransaction. LLM output is always 'suggested', never 'confirmed'.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

import httpx
from sqlmodel import Session, select

from .models import Category, Classification, ClassificationHistory, RawTransaction, Rule, Setting, now


# Kotak narration shapes, most specific first. Group 1 is the counterparty name.
_CP_PATTERNS = [
    re.compile(r"(?i)^recd:\s*(?:imps|neft|rtgs)/\d+/([^/]+)/"),            # Recd:IMPS/<ref>/<name>/<bank>/
    re.compile(r"(?i)^sentimps\d{6,}([^/]+)/"),                             # SentIMPS<ref><name>/<ifsc>/
    re.compile(r"(?i)^mb:\s*811\s*sent\s+(?:ft|neft|imps)\s+([a-z .]+?)\s+\d"),  # MB:811SENT FT <NAME> <acct>
    re.compile(r"(?i)^(?:neft|rtgs)\s+[a-z]{4}[a-z0-9]*\d{6,}\s+(.+)$"),    # NEFT <UTR> <NAME ...>
    re.compile(r"(?i)^upim?/([^/]+)/"),                                     # UPI/<name>/<ref>/<note>
    re.compile(r"(?i)^(?:imps|neft|rtgs|ib|mb)[\s/\-:]+(?:(?:cr|dr|p2a|p2m|in|out)[\s/\-:]+)?([^/\-:]+)"),
    re.compile(r"(?i)^cash\s+deposit\s+by\s+([a-z .]+?)\s+at\b"),           # Cash Deposit by <name> at <place>
]


def extract_counterparty(desc: str) -> str:
    d = re.sub(r"\s+", " ", desc.strip())
    for pat in _CP_PATTERNS:
        m = pat.search(d)
        if m:
            name = re.sub(r"\d{6,}", "", m.group(1))
            name = re.sub(r"\s+", " ", name).strip(" ./-")
            if len(name) >= 2 and not name.isdigit():
                return name.title()[:60]
    return ""


def _rule_matches(rule: Rule, tx: RawTransaction, cp: str) -> bool:
    direction = "credit" if tx.credit > 0 else "debit"
    if rule.direction != "any" and rule.direction != direction:
        return False
    amt = tx.credit or tx.debit
    if rule.min_amount is not None and amt < rule.min_amount:
        return False
    if rule.max_amount is not None and amt > rule.max_amount:
        return False
    text = tx.raw_description
    if rule.match_type == "exact":
        return cp.lower() == rule.pattern.lower() or text.lower() == rule.pattern.lower()
    if rule.match_type == "regex":
        try:
            return re.search(rule.pattern, text, re.I) is not None
        except re.error:
            return False
    return rule.pattern.lower() in text.lower()


def _record(s: Session, c: Classification) -> None:
    s.add(ClassificationHistory(raw_transaction_id=c.raw_transaction_id, category_id=c.category_id,
                                status=c.status, source=c.source, note=c.note))


def apply_rules(s: Session, txs: Iterable[RawTransaction], profile_id: int, only_unconfirmed: bool = True) -> int:
    rules = s.exec(select(Rule).where(Rule.profile_id == profile_id, Rule.enabled == True)  # noqa: E712
                   .order_by(Rule.priority, Rule.id)).all()
    changed = 0
    for tx in txs:
        c = s.exec(select(Classification).where(Classification.raw_transaction_id == tx.id)).first()
        if c is None:
            c = Classification(raw_transaction_id=tx.id, counterparty=extract_counterparty(tx.raw_description))
        if only_unconfirmed and c.status == "confirmed":
            continue
        if c.status != "confirmed":
            # Counterparty is derived data; refresh it when the extractor improves.
            cp = extract_counterparty(tx.raw_description)
            if cp != c.counterparty:
                c.counterparty = cp
                s.add(c)
        hit = next((r for r in rules if _rule_matches(r, tx, c.counterparty)), None)
        if hit is None:
            if c.id is None:
                s.add(c)
            continue
        new_status = "confirmed" if hit.auto_confirm else "suggested"
        if c.category_id != hit.category_id or c.status != new_status or c.source != "rule":
            c.category_id, c.status, c.source, c.rule_id = hit.category_id, new_status, "rule", hit.id
            c.confidence, c.updated_at = 1.0, now()
            s.add(c)
            s.flush()
            _record(s, c)
            changed += 1
    s.commit()
    return changed


def llm_suggest(s: Session, profile_id: int, limit: int = 40) -> dict:
    """Ask a local Ollama model to suggest categories for unclassified rows."""
    cfg = (s.get(Setting, "ollama") or Setting(key="ollama", value={})).value
    if not cfg.get("enabled"):
        return {"ok": False, "message": "Local AI is turned off in Settings."}
    cats = s.exec(select(Category).where(Category.profile_id == profile_id)).all()
    pending = s.exec(
        select(RawTransaction, Classification)
        .join(Classification, Classification.raw_transaction_id == RawTransaction.id)
        .where(Classification.status == "unclassified").limit(limit)).all()
    if not pending:
        return {"ok": True, "message": "Nothing to suggest.", "suggested": 0}

    by_dir = {d: [c.name for c in cats if c.direction == d] for d in ("credit", "debit")}
    done = 0
    try:
        with httpx.Client(base_url=cfg.get("url", "http://127.0.0.1:11434"), timeout=60) as client:
            for tx, c in pending:
                direction = "credit" if tx.credit else "debit"
                prompt = (
                    "You categorise Indian bank transactions. Reply with JSON only: "
                    '{"category": <one of the list>, "confidence": <0..1>}.\n'
                    f"Allowed categories: {json.dumps(by_dir[direction])}\n"
                    f"Direction: {direction}\nAmount: INR {(tx.credit or tx.debit) / 100:.2f}\n"
                    f"Bank narration: {tx.raw_description}"
                )
                r = client.post("/api/generate", json={"model": cfg.get("model", "qwen2.5:7b"), "prompt": prompt,
                                                        "stream": False, "format": "json",
                                                        "options": {"temperature": 0}})
                r.raise_for_status()
                try:
                    out = json.loads(r.json().get("response", "{}"))
                except json.JSONDecodeError:
                    continue
                cat = next((x for x in cats if x.direction == direction and x.name == out.get("category")), None)
                if cat is None:
                    continue
                c.category_id, c.status, c.source = cat.id, "suggested", "llm"
                c.confidence = float(out.get("confidence") or 0.5)
                c.updated_at = now()
                s.add(c)
                s.flush()
                _record(s, c)
                done += 1
    except httpx.HTTPError as e:
        s.commit()
        return {"ok": False, "message": f"Could not reach Ollama: {e}", "suggested": done}
    s.commit()
    return {"ok": True, "message": f"Suggested {done} of {len(pending)}.", "suggested": done}


def set_classification(s: Session, tx_id: int, category_id: Optional[int], note: Optional[str],
                       nature: Optional[str], confirm: bool = True) -> Classification:
    c = s.exec(select(Classification).where(Classification.raw_transaction_id == tx_id)).first()
    if c is None:
        c = Classification(raw_transaction_id=tx_id)
    if category_id is not None:
        c.category_id = category_id
    if note is not None:
        c.note = note
    if nature is not None:
        c.nature = nature
    c.source = "user"
    c.status = "confirmed" if (confirm and c.category_id) else ("suggested" if c.category_id else "unclassified")
    c.confidence, c.updated_at = 1.0, now()
    s.add(c)
    s.flush()
    _record(s, c)
    return c
