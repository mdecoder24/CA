"""Database tables.

Money is stored as integer paise everywhere to avoid floating-point drift.
Raw bank data (RawTransaction) is write-once; all interpretation lives in
Classification and related tables so original evidence is never altered.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now().astimezone()


class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    bank: str = "kotak"
    masked_number: str = ""
    nickname: str = "Kotak Savings"


class ImportBatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    filename: str
    sha256: str = Field(index=True, unique=True)
    stored_path: str
    file_type: str
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    opening_balance: Optional[int] = None
    closing_balance: Optional[int] = None
    rows_parsed: int = 0
    rows_inserted: int = 0
    rows_duplicate: int = 0
    # ok | reordered | override | failed
    status: str = "ok"
    reconcile_detail: str = ""
    override_reason: str = ""
    created_at: datetime = Field(default_factory=now)


class RawTransaction(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("account_id", "fingerprint"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    import_batch_id: int = Field(foreign_key="importbatch.id")
    row_index: int
    txn_date: date = Field(index=True)
    value_date: Optional[date] = None
    raw_description: str
    ref_no: str = ""
    debit: int = 0  # paise
    credit: int = 0  # paise
    balance: Optional[int] = None  # paise
    fingerprint: str


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    name: str
    direction: str  # credit | debit
    treatment: str  # see tax.engine.TREATMENTS
    sort: int = 0


class Classification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    raw_transaction_id: int = Field(foreign_key="rawtransaction.id", unique=True)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    nature: str = "personal"  # personal | business
    source: str = "none"  # none | rule | llm | user
    status: str = "unclassified"  # unclassified | suggested | confirmed
    confidence: Optional[float] = None
    rule_id: Optional[int] = None
    counterparty: str = ""
    note: str = ""
    updated_at: datetime = Field(default_factory=now)


class ClassificationHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    raw_transaction_id: int = Field(index=True)
    category_id: Optional[int] = None
    status: str
    source: str
    note: str = ""
    changed_at: datetime = Field(default_factory=now)


class Rule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    priority: int = 100  # lower runs first
    match_type: str = "contains"  # contains | regex | exact
    pattern: str
    direction: str = "any"  # credit | debit | any
    min_amount: Optional[int] = None  # paise
    max_amount: Optional[int] = None  # paise
    category_id: int = Field(foreign_key="category.id")
    auto_confirm: bool = False
    builtin: bool = False
    enabled: bool = True


class Flag(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("raw_transaction_id", "type"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    raw_transaction_id: int = Field(foreign_key="rawtransaction.id", index=True)
    type: str
    detail: str = ""
    resolved: bool = False
    resolution_note: str = ""


class TaxInput(SQLModel, table=True):
    """Manual tax inputs for one profile and financial year.

    `data` holds a JSON document; see tax.engine.DEFAULT_INPUTS for its shape.
    """

    __table_args__ = (UniqueConstraint("profile_id", "fy"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    fy: str  # e.g. "2025-26"
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entity: str
    entity_id: int
    action: str
    before: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    after: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    at: datetime = Field(default_factory=now)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON))
