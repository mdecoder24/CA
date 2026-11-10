"""Kotak Mahindra Bank statement parser.

Kotak offers statements in several layouts (net-banking CSV/XLS, app
downloads, monthly PDF e-statements). Rather than hard-coding one layout,
the parser turns the file into a grid of cells, finds the header row by
keywords, maps columns by name, and reads rows below it. It supports both:

  * separate Withdrawal (Dr) / Deposit (Cr) columns, and
  * a single Amount column with a Dr/Cr indicator column or suffix.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .base import ParsedRow, ParsedStatement, PasswordRequired, StatementError

DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %b %y", "%d/%b/%Y",
    "%d-%B-%Y", "%d %B %Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
]

HEADER_KEYS = {
    "date": [r"^(txn|transaction|tran)?\.?\s*date$", r"^date$", r"posting\s*date", r"^txn\s*dt"],
    "value_date": [r"value\s*date", r"^value\s*dt"],
    "description": [r"description", r"narration", r"particulars", r"remarks", r"details"],
    "ref": [r"chq", r"cheque", r"ref", r"instrument"],
    "debit": [r"withdrawal", r"^debit", r"\bdr\.?\s*amount", r"debit\s*amount", r"^dr$"],
    "credit": [r"deposit", r"^credit", r"\bcr\.?\s*amount", r"credit\s*amount", r"^cr$"],
    "amount": [r"^amount", r"transaction\s*amount"],
    "drcr": [r"^dr\s*/\s*cr$", r"^cr\s*/\s*dr$", r"^type$", r"debit\s*/\s*credit", r"^dr/cr$"],
    "balance": [r"balance"],
}

AMOUNT_RE = re.compile(r"-?\(?[\d,]+(?:\.\d{1,2})?\)?")


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).replace(" ", " ").strip()
    return "" if s.lower() in {"nan", "none", "nat"} else s


def parse_date(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _clean(v)
    if not s:
        return None
    s = re.sub(r"\s+", " ", s)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # A date followed by a time, e.g. "01-04-2025 10:22:11"
    m = re.match(r"^(\S+)\s+\d{1,2}:\d{2}", s)
    if m:
        return parse_date(m.group(1))
    return None


def parse_amount(v) -> tuple[Optional[int], Optional[str]]:
    """Return (paise, 'dr'|'cr'|None). Blank or dash -> (None, None)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if v != v:  # NaN
            return None, None
        return round(float(v) * 100), None
    s = _clean(v)
    if not s or s in {"-", "--"}:
        return None, None
    side = None
    low = s.lower()
    if re.search(r"\bcr\.?$|\(cr\)$", low):
        side = "cr"
    elif re.search(r"\bdr\.?$|\(dr\)$", low):
        side = "dr"
    s2 = re.sub(r"(?i)(₹|rs\.?|inr|\(cr\)|\(dr\)|\bcr\.?|\bdr\.?)", "", s).replace(" ", "")
    m = AMOUNT_RE.fullmatch(s2)
    if not m:
        return None, None
    neg = s2.startswith("-") or (s2.startswith("(") and s2.endswith(")"))
    num = s2.strip("-()").replace(",", "")
    if not num:
        return None, None
    paise = round(float(num) * 100)
    return (-paise if neg else paise), side


def _match_header(cell: str) -> Optional[str]:
    c = re.sub(r"\s+", " ", cell.lower()).strip(" .:")
    if not c:
        return None
    # value date must be checked before date
    for key in ["value_date", "drcr", "date", "description", "debit", "credit", "amount", "balance", "ref"]:
        for pat in HEADER_KEYS[key]:
            if re.search(pat, c):
                return key
    return None


def _find_header(grid: list[list[str]]) -> tuple[int, dict[str, int]]:
    for i, row in enumerate(grid[:200]):
        mapping: dict[str, int] = {}
        for j, cell in enumerate(row):
            key = _match_header(_clean(cell))
            if key and key not in mapping:
                mapping[key] = j
        has_money = ("debit" in mapping and "credit" in mapping) or "amount" in mapping
        if "date" in mapping and "description" in mapping and has_money:
            return i, mapping
    raise StatementError("Could not find the transaction table header (Date / Description / Amount columns).")


OPENING_RE = re.compile(r"opening\s+balance[^\d\-]*(-?[\d,]+\.\d{2})\s*(cr|dr)?", re.I)
CLOSING_RE = re.compile(r"closing\s+balance[^\d\-]*(-?[\d,]+\.\d{2})\s*(cr|dr)?", re.I)
ACCOUNT_RE = re.compile(r"(?:account\s*(?:no|number)|a/c\s*no)\.?\s*[:\-]?\s*([X\d*]{4,})", re.I)


def _balance_from_match(m) -> Optional[int]:
    if not m:
        return None
    val, _ = parse_amount(m.group(1))
    if val is not None and m.group(2) and m.group(2).lower() == "dr":
        val = -abs(val)
    return val


def _grid_to_statement(grid: list[list[str]], full_text: str) -> ParsedStatement:
    h, cols = _find_header(grid)
    header_row = [_clean(c).lower() for c in grid[h]]

    # A Dr/Cr column that sits right after Balance describes the balance, not the amount.
    bal_side_col = None
    if "balance" in cols:
        nxt = cols["balance"] + 1
        if nxt < len(header_row) and _match_header(header_row[nxt]) == "drcr":
            bal_side_col = nxt
            if cols.get("drcr") == nxt:
                del cols["drcr"]
    if "amount" in cols and "drcr" not in cols:
        nxt = cols["amount"] + 1
        if nxt < len(header_row) and _match_header(header_row[nxt]) == "drcr":
            cols["drcr"] = nxt

    def cell(row, key):
        j = cols.get(key)
        return row[j] if j is not None and j < len(row) else ""

    rows: list[ParsedRow] = []
    opening = None
    for raw in grid[h + 1:]:
        if not any(_clean(c) for c in raw):
            continue
        # Repeated header on a new PDF page
        if _match_header(_clean(cell(raw, "date"))) == "date":
            continue
        desc = re.sub(r"\s+", " ", _clean(cell(raw, "description")))
        d = parse_date(cell(raw, "date"))
        if d is None:
            low = " ".join(_clean(c).lower() for c in raw)
            if "opening balance" in low and opening is None:
                bal, _ = parse_amount(cell(raw, "balance"))
                opening = bal
                continue
            if any(k in low for k in ("closing balance", "total", "statement summary", "end of statement")):
                if rows:
                    break
                continue
            # Multi-line narration wrapped onto the next row
            if desc and rows:
                rows[-1].description = f"{rows[-1].description} {desc}".strip()
            continue

        if "opening balance" in desc.lower() and not _clean(cell(raw, "debit")) and not _clean(cell(raw, "credit")):
            opening, _ = parse_amount(cell(raw, "balance"))
            continue

        debit = credit = 0
        if "amount" in cols and not ("debit" in cols and "credit" in cols):
            amt, side = parse_amount(cell(raw, "amount"))
            if amt is None:
                continue
            ind = _clean(cell(raw, "drcr")).lower()
            if ind.startswith("d"):
                side = "dr"
            elif ind.startswith("c"):
                side = "cr"
            if side is None:
                side = "dr" if amt < 0 else "cr"
            if side == "dr":
                debit = abs(amt)
            else:
                credit = abs(amt)
        else:
            dv, _ = parse_amount(cell(raw, "debit"))
            cv, _ = parse_amount(cell(raw, "credit"))
            debit, credit = abs(dv or 0), abs(cv or 0)
            if debit == 0 and credit == 0:
                continue

        bal, bside = parse_amount(cell(raw, "balance"))
        if bal is not None:
            if bal_side_col is not None and _clean(raw[bal_side_col] if bal_side_col < len(raw) else "").lower().startswith("d"):
                bal = -abs(bal)
            elif bside == "dr":
                bal = -abs(bal)

        rows.append(ParsedRow(
            txn_date=d,
            value_date=parse_date(cell(raw, "value_date")),
            description=desc,
            ref_no=_clean(cell(raw, "ref")),
            debit=debit,
            credit=credit,
            balance=bal,
        ))

    if not rows:
        raise StatementError("The statement table was found but contained no transactions.")

    # Some downloads list newest first; normalise to oldest first.
    if rows[0].txn_date > rows[-1].txn_date:
        rows.reverse()

    if opening is None:
        opening = _balance_from_match(OPENING_RE.search(full_text))
    closing = _balance_from_match(CLOSING_RE.search(full_text))
    acct = ACCOUNT_RE.search(full_text)
    masked = ""
    if acct:
        digits = re.sub(r"\D", "", acct.group(1))
        masked = f"XXXX{digits[-4:]}" if digits else ""
    return ParsedStatement(rows=rows, opening_balance=opening, closing_balance=closing, masked_account=masked)


def _read_csv(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def _read_excel(path: Path, file_type: str) -> list[list[str]]:
    import pandas as pd

    engine = "xlrd" if file_type == "xls" else "openpyxl"
    try:
        sheets = pd.read_excel(path, header=None, sheet_name=None, engine=engine, dtype=object)
    except Exception as e:  # noqa: BLE001
        # Many bank "XLS" downloads are really HTML tables.
        try:
            tables = pd.read_html(path)
            sheets = {i: t for i, t in enumerate(tables)}
        except Exception:
            raise StatementError(f"Could not read spreadsheet: {e}") from e
    grid: list[list[str]] = []
    for df in sheets.values():
        for row in df.itertuples(index=False):
            grid.append([v if isinstance(v, (datetime, date)) else _clean(v) for v in row])
    return grid


def _read_pdf(path: Path, password: Optional[str]) -> tuple[list[list[str]], str]:
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    try:
        pdf = pdfplumber.open(path, password=password or "")
    except PDFPasswordIncorrect as e:
        raise PasswordRequired("This PDF is password-protected. Enter the statement password.") from e
    except Exception as e:  # noqa: BLE001
        if "password" in str(e).lower() or "encrypt" in str(e).lower():
            raise PasswordRequired("This PDF is password-protected. Enter the statement password.") from e
        raise StatementError(f"Could not open PDF: {e}") from e

    grid: list[list[str]] = []
    texts: list[str] = []
    with pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
            tables = page.extract_tables() or []
            if not tables:
                tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"}) or []
            for t in tables:
                for r in t:
                    grid.append([_clean(c).replace("\n", " ") for c in r])
    return grid, "\n".join(texts)


class KotakParser:
    bank = "kotak"

    def parse(self, path: Path, file_type: str, password: Optional[str] = None) -> ParsedStatement:
        file_type = file_type.lower()
        if file_type == "csv":
            grid = _read_csv(path.read_bytes())
            text = "\n".join(",".join(map(str, r)) for r in grid[:60])
        elif file_type in ("xls", "xlsx"):
            grid = _read_excel(path, file_type)
            text = "\n".join(" ".join(map(str, r)) for r in grid[:60])
        elif file_type == "pdf":
            grid, text = _read_pdf(path, password)
        else:
            raise StatementError(f"Unsupported file type: {file_type}. Use CSV, XLS, XLSX or PDF.")
        return _grid_to_statement(grid, text)
