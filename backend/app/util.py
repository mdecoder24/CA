from datetime import date

from sqlmodel import Session

from .models import AuditLog


def fy_of(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_range(fy: str) -> tuple[date, date]:
    start = int(fy.split("-")[0])
    return date(start, 4, 1), date(start + 1, 3, 31)


def audit(s: Session, entity: str, entity_id: int, action: str, before=None, after=None) -> None:
    s.add(AuditLog(entity=entity, entity_id=entity_id, action=action, before=_jsonable(before), after=_jsonable(after)))


def _jsonable(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(obj).items()}
