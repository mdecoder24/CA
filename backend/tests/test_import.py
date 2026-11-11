import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.importers.base import ParsedRow, ParsedStatement
from app.importers.kotak import KotakParser, parse_amount, parse_date
from app.importers.reconcile import reconcile

from .conftest import KOTAK_CSV


def _upload(client, name, data: bytes, **form):
    return client.post("/api/imports", files={"file": (name, io.BytesIO(data))}, data={"account_id": 1, **form})


def test_parse_helpers():
    assert parse_amount("1,34,550.00") == (13455000, None)
    assert parse_amount("450.00 Dr") == (45000, "dr")
    assert parse_amount("(100.00)") == (-10000, None)
    assert parse_amount("-") == (None, None)
    assert parse_date("01-04-2025").isoformat() == "2025-04-01"
    assert parse_date("01 Apr 2025").isoformat() == "2025-04-01"
    assert parse_date("01/04/25").isoformat() == "2025-04-01"


def test_csv_import_classifies_and_flags(client):
    r = _upload(client, "kotak_apr.csv", KOTAK_CSV.encode())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 6
    assert body["batch"]["status"] == "ok"
    assert body["batch"]["opening_balance"] == 10_000_00

    txs = client.get("/api/transactions", params={"fy": "2025-26"}).json()
    by_desc = {t["raw_description"][:12]: t for t in txs}
    assert by_desc["NEFT ACME TE"]["category"] == "Salary"
    assert by_desc["NEFT ACME TE"]["status"] == "suggested"
    assert by_desc["Int.Pd:01-04"]["category"] == "Interest – savings"
    assert by_desc["Int.Pd:01-04"]["status"] == "confirmed"
    assert by_desc["IMPS/ZERODHA"]["category"] == "Trading – funds to broker"
    assert by_desc["UPI/SWIGGY/5"]["category"] == "Food & groceries"
    # Raw narration preserved exactly
    assert by_desc["UPI/RAHUL SH"]["raw_description"] == "UPI/RAHUL SHARMA/509399999999/consulting"
    assert by_desc["UPI/RAHUL SH"]["counterparty"] == "Rahul Sharma"
    flag_types = {f["type"] for t in txs for f in t["flags"]}
    assert {"large_credit", "cash_deposit"} <= flag_types


def test_same_file_twice_rejected(client):
    assert _upload(client, "a.csv", KOTAK_CSV.encode()).status_code == 200
    r = _upload(client, "a.csv", KOTAK_CSV.encode())
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "duplicate_file"


def test_overlapping_statement_skips_duplicates(client):
    assert _upload(client, "a.csv", KOTAK_CSV.encode()).status_code == 200
    extra = KOTAK_CSV + '7,30-04-2025,30-04-2025,UPI/AMAZON/5000/order,UPI0003,862.00,DR,"1,59,000.00",CR\n'
    r = _upload(client, "b.csv", extra.encode())
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 1
    assert r.json()["duplicates"] == 6


def test_broken_chain_fails_then_override(client):
    broken = KOTAK_CSV.replace('"94,550.00"', '"94,000.00"')
    r = _upload(client, "broken.csv", broken.encode())
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "reconcile_failed"
    assert "Row 2" in d["message"]
    r = _upload(client, "broken.csv", broken.encode(), override_reason="Checked against passbook; bank misprint")
    assert r.status_code == 200
    assert r.json()["batch"]["status"] == "override"
    log = client.get("/api/audit").json()
    assert any(a["after"] and a["after"].get("override_reason") for a in log)


def test_same_day_reorder():
    from datetime import date

    d = date(2025, 4, 1)
    rows = [
        ParsedRow(d, "b", debit=0, credit=500, balance=1600),  # listed first but happened second
        ParsedRow(d, "a", debit=0, credit=100, balance=1100),
    ]
    res = reconcile(ParsedStatement(rows=rows, opening_balance=1000))
    assert res.status == "reordered"
    assert [r.description for r in res.rows] == ["a", "b"]


def test_xlsx_withdrawal_deposit_layout(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Kotak Mahindra Bank"])
    ws.append(["Opening Balance", "5,000.00"])
    ws.append([])
    ws.append(["Date", "Narration", "Chq/Ref No", "Withdrawal (Dr)", "Deposit (Cr)", "Balance"])
    ws.append(["02/05/2025", "UPI/BLINKIT/1/grocery", "R1", 200, None, 4800])
    ws.append(["", "continued narration", "", None, None, None])
    ws.append(["03/05/2025", "NEFT CLIENT CO FEES", "R2", None, 10000, 14800])
    p = tmp_path / "s.xlsx"
    wb.save(p)
    st = KotakParser().parse(p, "xlsx")
    assert len(st.rows) == 2
    assert st.rows[0].description == "UPI/BLINKIT/1/grocery continued narration"
    assert st.rows[0].debit == 20000 and st.rows[1].credit == 10_000_00
    assert reconcile(st).status == "ok"


def _make_pdf(path: Path, password: str | None = None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.pdfencrypt import StandardEncryption
    from reportlab.platypus import SimpleDocTemplate, Table, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    enc = StandardEncryption(password, canPrint=1) if password else None
    doc = SimpleDocTemplate(str(path), pagesize=A4, encrypt=enc)
    data = [["Date", "Description", "Chq/Ref No.", "Withdrawal (Dr.)", "Deposit (Cr.)", "Balance"]]
    data.append(["01-06-2025", "Opening Balance", "", "", "", "1,000.00"])
    data.append(["02-06-2025", "UPI/ZOMATO/1/dinner", "U1", "250.00", "", "750.00"])
    data.append(["05-06-2025", "SALARY JUNE ACME", "N1", "", "50,000.00", "50,750.00"])
    doc.build([Paragraph("Account No: XXXXXX9876", getSampleStyleSheet()["BodyText"]), Table(data)])


def test_pdf_import(tmp_path):
    p = tmp_path / "s.pdf"
    _make_pdf(p)
    st = KotakParser().parse(p, "pdf")
    assert [r.description for r in st.rows] == ["UPI/ZOMATO/1/dinner", "SALARY JUNE ACME"]
    assert st.opening_balance == 1_000_00
    assert reconcile(st).status == "ok"
    assert st.masked_account == "XXXX9876"


def test_password_pdf(client, tmp_path):
    p = tmp_path / "locked.pdf"
    _make_pdf(p, password="secret1")
    r = _upload(client, "locked.pdf", p.read_bytes())
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "password_required"
    r = _upload(client, "locked.pdf", p.read_bytes(), password="secret1")
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 2


def test_kotak_summary_table_closing_balance(tmp_path):
    """Kotak e-statement summary: header row then values row; closing is the 2nd number."""
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

    p = tmp_path / "s.pdf"
    doc = SimpleDocTemplate(str(p))
    st = getSampleStyleSheet()["BodyText"]
    data = [["#", "Date", "Description", "Chq/Ref. No.", "Withdrawal (Dr.)", "Deposit (Cr.)", "Balance"],
            ["-", "-", "Opening Balance", "-", "-", "-", "6,923.82"],
            ["1", "01 Apr 2026", "UPI/SHOP/1/x", "UPI-1", "1,423.82", "", "5,500.00"]]
    doc.build([Table(data), Paragraph("Account Summary", st),
               Table([["Particulars", "Opening Balance", "Closing Balance"],
                      ["Savings Account (SA):", "6,923.82", "5,500.00"]], colWidths=[150, 150, 150])])
    parsed = KotakParser().parse(p, "pdf")
    assert parsed.opening_balance == 692382
    assert parsed.closing_balance == 550000
    assert reconcile(parsed).status == "ok"


def test_counterparty_kotak_shapes():
    from app.classify import extract_counterparty as cp

    assert cp("Recd:IMPS/609812695897/Nandanavan/KKBK/ X8303/Bill") == "Nandanavan"
    assert cp("SentIMPS613809205786Chaitanya /HDFCX9403/V") == "Chaitanya"
    assert cp("MB:811SENT FT HRISHIKESH 8143581810 KOTAK") == "Hrishikesh"
    assert cp("NEFT HDFCH00995043028 HDFC MUTUAL FUND REDEMPTION") == "Hdfc Mutual Fund Redemption"
    assert cp("RTGS UTIBR72026091100099294 PAYU PAYMENTS PVT L") == "Payu Payments Pvt L"
    assert cp("UPI/SAGAR FOOD COUR/645749021858/Pay To SAGAR FO") == "Sagar Food Cour"
    assert cp("UPIM/NATIONAL STOCK EXCHANGE OF INDIA/663161754741") == "National Stock Exchange Of India"
    assert cp("Cash Deposit by ramesh at SAROORNAGAR HYDERABAD") == "Ramesh"
    assert cp("CASHBACK EARNED") == ""


def test_same_amount_same_day_different_refs_not_duplicate(client):
    csv = KOTAK_CSV.replace(
        '6,30-04-2025,30-04-2025,Int.Pd:01-04-2025 to 30-04-2025,,312.00,CR,"1,59,862.00",CR\n',
        '6,30-04-2025,30-04-2025,UPI/HARI/1/x,UPI-A,900.00,DR,"1,58,650.00",CR\n'
        '7,30-04-2025,30-04-2025,UPI/HARI/2/x,UPI-B,900.00,DR,"1,57,750.00",CR\n')
    assert _upload(client, "d.csv", csv.encode()).status_code == 200
    txs = client.get("/api/transactions", params={"fy": "2025-26"}).json()
    assert not any(f["type"] == "possible_duplicate" for t in txs for f in t["flags"])
