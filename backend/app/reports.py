"""CA pack: Excel workbook + PDF summary for one financial year."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from .models import now
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlmodel import Session, select

from .db import data_dir
from .models import Flag, ImportBatch
from .summary import HEAD_OF, coverage_gaps, dashboard, fy_rows, tax_estimate

INR = '[$₹-4009]#,##,##0.00;[Red]-[$₹-4009]#,##,##0.00'
BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="E8ECEF")
DISCLAIMER = "Estimate only. Confirm with your CA before filing. Original bank narrations are reproduced unaltered."


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], money_cols: tuple[int, ...] = ()):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = BOLD, HEAD_FILL
    for r in rows:
        ws.append(r)
    for col in money_cols:
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                c.number_format = INR
    for i, h in enumerate(header, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:500] if i - 1 < len(r)] + [8])
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 70)
    ws.freeze_panes = "A2"
    return ws


def _ordered_labels(est: dict) -> list[str]:
    """Merge both regimes' line labels, keeping computation order."""
    out: list[str] = []
    for ln in est["regimes"]["old"]["lines"] + est["regimes"]["new"]["lines"]:
        if ln["label"] not in out:
            out.append(ln["label"])
    return out


def _pdf_text(s: str) -> str:
    """Built-in PDF fonts lack ₹ and Paragraph parses XML, so escape and swap the symbol."""
    from xml.sax.saxutils import escape

    return escape(str(s).replace("₹", "Rs "))


def _r(paise: int | None) -> float | None:
    return None if paise is None else paise / 100


def build_excel(s: Session, fy: str) -> Path:
    rows = fy_rows(s, fy)
    est = tax_estimate(s, fy)
    dash = dashboard(s, fy)
    flags = defaultdict(list)
    for f in s.exec(select(Flag)):
        flags[f.raw_transaction_id].append(f)

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"FinTrack — CA pack — {est['label']}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([DISCLAIMER])
    ws.append([f"Generated {now():%d %b %Y %H:%M}"])
    ws.append([])
    summary = [
        ("Total credits", _r(dash["total_credits"])),
        ("Total debits", _r(dash["total_debits"])),
        ("Closing balance", _r(dash["closing_balance"])),
        ("Transactions", dash["txn_count"]),
        ("Credits not yet confirmed", dash["unclassified_credits"]),
        ("Amount of unconfirmed credits", _r(dash["unclassified_credit_amount"])),
        ("Open flags", dash["open_flags"]),
        ("Statement gaps", "; ".join(f"{g['from']} to {g['to']}" for g in dash["gaps"]) or "None"),
    ]
    for k, v in summary:
        ws.append([k, v])
        if isinstance(v, float):
            ws.cell(ws.max_row, 2).number_format = INR
    ws.append([])
    ws.append(["Income by head (confirmed credits)"])
    ws.cell(ws.max_row, 1).font = BOLD
    for h in dash["income_heads"]:
        ws.append([h["head"], _r(h["amount"])])
        ws.cell(ws.max_row, 2).number_format = INR
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 22

    tx_rows, credit_cat, debit_cat, interest, trading, cash, flagged = [], defaultdict(int), defaultdict(int), [], [], [], []
    for tx, c, cat in rows:
        cname = cat.name if cat else ""
        status = c.status if c else "unclassified"
        fl = flags.get(tx.id, [])
        base = [tx.txn_date, tx.value_date, tx.raw_description, tx.ref_no, _r(tx.debit) or None, _r(tx.credit) or None,
                _r(tx.balance)]
        tx_rows.append(base + [cname, HEAD_OF.get(cat.treatment, "") if cat and tx.credit else "", status,
                               c.source if c else "", c.note if c else "", "; ".join(f.type for f in fl)])
        if tx.credit:
            credit_cat[cname or "(unclassified)"] += tx.credit
        else:
            debit_cat[cname or "(unclassified)"] += tx.debit
        if cat and cat.treatment in ("interest_savings", "interest_other"):
            interest.append([tx.txn_date, tx.raw_description, cname, _r(tx.credit)])
        if cat and cat.treatment == "trading_capital":
            trading.append([tx.txn_date, tx.raw_description, _r(tx.debit) or None, _r(tx.credit) or None])
        if any(f.type == "cash_deposit" for f in fl):
            cash.append([tx.txn_date, tx.raw_description, _r(tx.credit), c.note if c else ""])
        if tx.credit and (status != "confirmed" or (cat and cat.treatment == "unexplained") or any(not f.resolved for f in fl)):
            flagged.append([tx.txn_date, tx.raw_description, _r(tx.credit), cname or "(unclassified)", status,
                            "; ".join(f.detail for f in fl), "; ".join(f.resolution_note for f in fl if f.resolution_note),
                            c.note if c else ""])

    _sheet(wb, "All transactions",
           ["Date", "Value date", "Bank narration (original)", "Ref / Chq", "Debit", "Credit", "Balance",
            "Category", "Income head", "Status", "Classified by", "Note", "Flags"], tx_rows, (5, 6, 7))
    _sheet(wb, "Credits by category", ["Category", "Amount"],
           [[k, _r(v)] for k, v in sorted(credit_cat.items(), key=lambda x: -x[1])], (2,))
    _sheet(wb, "Debits by category", ["Category", "Amount"],
           [[k, _r(v)] for k, v in sorted(debit_cat.items(), key=lambda x: -x[1])], (2,))
    _sheet(wb, "Income by head", ["Head", "Amount"], [[h["head"], _r(h["amount"])] for h in dash["income_heads"]], (2,))
    _sheet(wb, "Interest", ["Date", "Narration", "Category", "Amount"], interest, (4,))
    t_in = sum(r[3] or 0 for r in trading)
    t_out = sum(r[2] or 0 for r in trading)
    _sheet(wb, "Trading flows", ["Date", "Narration", "To broker", "From broker"],
           trading + [[None, "TOTAL", t_out, t_in], [None, "NET (from − to)", None, t_in - t_out]], (3, 4))
    _sheet(wb, "Cash deposits", ["Date", "Narration", "Amount", "Note"], cash, (3,))
    _sheet(wb, "Flagged & unexplained", ["Date", "Narration", "Amount", "Category", "Status", "Flags",
                                          "Resolution", "Note"], flagged, (3,))

    tax_rows = []
    old_by = {ln["label"]: ln for ln in est["regimes"]["old"]["lines"]}
    new_by = {ln["label"]: ln for ln in est["regimes"]["new"]["lines"]}
    for lb in _ordered_labels(est):
        n, o = new_by.get(lb), old_by.get(lb)
        tax_rows.append([lb, n["amount"] if n else None, o["amount"] if o else None,
                         (n or o)["source"]])
    tax_rows += [[], ["Recommended regime", est["regimes"][est["recommended"]]["name"]], [], ["Notes"]]
    tax_rows += [[n] for n in est["notes"]] + [[est["disclaimer"]]]
    _sheet(wb, "Tax estimate", ["Line", "New regime", "Old regime", "Source"], tax_rows, (2, 3))

    batches = s.exec(select(ImportBatch).order_by(ImportBatch.created_at)).all()
    _sheet(wb, "Import log", ["Imported at", "File", "SHA-256", "Period from", "Period to", "Rows parsed",
                              "Inserted", "Duplicates skipped", "Reconciliation", "Detail", "Override reason"],
           [[b.created_at.replace(tzinfo=None), b.filename, b.sha256, b.period_from, b.period_to, b.rows_parsed, b.rows_inserted,
             b.rows_duplicate, b.status, b.reconcile_detail, b.override_reason] for b in batches])
    gaps = coverage_gaps(s, fy)
    if gaps:
        _sheet(wb, "Statement gaps", ["From", "To"], [[g["from"], g["to"]] for g in gaps])

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for c in row:
                if isinstance(c.value, datetime):
                    c.number_format = "DD-MM-YYYY HH:MM"
                    c.alignment = Alignment(horizontal="left")
                elif c.value.__class__.__name__ == "date":
                    c.number_format = "DD-MM-YYYY"
                    c.alignment = Alignment(horizontal="left")

    out = data_dir() / "exports" / f"FinTrack_CA_pack_FY{fy}_{now():%Y%m%d_%H%M%S}.xlsx"
    wb.save(out)
    return out


def build_pdf(s: Session, fy: str) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    est = tax_estimate(s, fy)
    dash = dashboard(s, fy)
    out = data_dir() / "exports" / f"FinTrack_summary_FY{fy}_{now():%Y%m%d_%H%M%S}.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=f"FinTrack FY {fy}")
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=8, leading=10)

    # Built-in PDF fonts lack the rupee glyph, so amounts use "Rs".
    def inr(rupees):
        if rupees is None:
            return "-"
        from .tax.engine import inr as _inr

        return f"Rs {_inr(rupees)}"

    def tbl(data, widths, right=(1,)):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8ECEF")),
            *[("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right], ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9CED3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    flow = [Paragraph(f"FinTrack — {est['label']}", st["Title"]),
            Paragraph(f"<b>{_pdf_text(est['disclaimer'])}</b> Generated {now():%d %b %Y}.", st["BodyText"]),
            Spacer(1, 6)]
    flow.append(tbl([["Summary", "Value"],
                     ["Total credits", inr(dash["total_credits"] / 100)],
                     ["Total debits", inr(dash["total_debits"] / 100)],
                     ["Closing balance", inr((dash["closing_balance"] or 0) / 100)],
                     ["Credits not yet confirmed", f"{dash['unclassified_credits']} "
                                                   f"({inr(dash['unclassified_credit_amount'] / 100)})"],
                     ["Open flags", str(dash["open_flags"])],
                     ["Statement gaps", "; ".join(f"{g['from']} to {g['to']}" for g in dash["gaps"]) or "None"]],
                    [80 * mm, 98 * mm]))
    flow += [Spacer(1, 8), Paragraph("Income by head (confirmed credits)", st["Heading3"])]
    flow.append(tbl([["Head", "Amount"]] + [[h["head"], inr(h["amount"] / 100)] for h in dash["income_heads"]],
                    [80 * mm, 98 * mm]))

    flow += [Spacer(1, 8), Paragraph("Tax estimate — old vs new regime", st["Heading3"])]
    new_by = {ln["label"]: ln["amount"] for ln in est["regimes"]["new"]["lines"]}
    old_by = {ln["label"]: ln["amount"] for ln in est["regimes"]["old"]["lines"]}
    labels = _ordered_labels(est)
    flow.append(tbl([["Line", "New regime", "Old regime"]] +
                    [[Paragraph(_pdf_text(lb), small), inr(new_by.get(lb)), inr(old_by.get(lb))] for lb in labels],
                    [100 * mm, 39 * mm, 39 * mm], right=(1, 2)))
    flow.append(Paragraph(f"Lower liability: <b>{_pdf_text(est['regimes'][est['recommended']]['name'])}</b>", st["BodyText"]))
    for n in est["notes"]:
        flow.append(Paragraph(f"• {_pdf_text(n)}", small))

    rows = fy_rows(s, fy)
    flags = defaultdict(list)
    for f in s.exec(select(Flag).where(Flag.resolved == False)):  # noqa: E712
        flags[f.raw_transaction_id].append(f.detail)
    flagged = [[tx.txn_date.strftime("%d-%m-%Y"), Paragraph(_pdf_text(tx.raw_description[:90]), small), inr(tx.credit / 100),
                Paragraph(_pdf_text("; ".join(flags.get(tx.id, [])) or (c.status if c else "unclassified")), small)]
               for tx, c, cat in rows if tx.credit and (flags.get(tx.id) or not c or c.status != "confirmed"
                                                        or (cat and cat.treatment == "unexplained"))]
    if flagged:
        flow += [Spacer(1, 8), Paragraph(f"Credits needing explanation ({len(flagged)})", st["Heading3"])]
        flow.append(tbl([["Date", "Narration", "Amount", "Why"]] + flagged[:150],
                        [20 * mm, 78 * mm, 25 * mm, 55 * mm], right=(2,)))
        if len(flagged) > 150:
            flow.append(Paragraph(f"…and {len(flagged) - 150} more in the Excel workbook.", small))
    doc.build(flow)
    return out
