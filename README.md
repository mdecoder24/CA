# FinTrack

FinTrack is a personal finance and tax-preparation tool for one person in India. It runs only on your own computer. Your bank data is never sent anywhere.

You add your bank accounts (Kotak, HDFC, ICICI, SBI, Axis and others), upload their statements, and FinTrack does four things:

1. **Explains every credit and debit.** Rules and an optional local AI suggest a category. You confirm each one in the Review screen. Unusual items are flagged: large credits, cash deposits, repeated round amounts, and duplicate bank references.
2. **Analyses your spending.** It shows where the money went, which payees you paid most, what was only moved between your own accounts, and a spending risk score from 0 to 100 with the reasons behind it. A snapshot appears right after each upload.
3. **Estimates tax** under the old and the new regime, net of TDS and advance tax. It counts **confirmed** income only. Transfers, refunds, loans and trading capital are never counted as income.
4. **Builds a CA pack:** an Excel workbook and a PDF summary for your Chartered Accountant.

Original bank rows are stored exactly as the bank printed them and are never edited. Classification, spend analysis and tax all live in separate tables.

---

## 1. Requirements

| Tool | Version | Install (macOS) |
|---|---|---|
| Python | 3.11 or newer (3.12 recommended) | `brew install python@3.12` |
| Node.js | 20 or newer | `brew install node` |
| pnpm | any recent | `brew install pnpm` or `npm i -g pnpm` |
| Ollama (optional) | any | https://ollama.com |

FinTrack is free. It uses only open-source software and runs locally.

---

## 2. First-time setup and run

From the project folder:

```bash
./dev.sh
```

The first run does the following automatically:

1. Creates `backend/.venv` and installs the Python packages in `backend/requirements.txt`.
2. Installs the frontend packages with `pnpm install` in `frontend/`.
3. Warns you if macOS FileVault is off.
4. Starts the backend on `http://127.0.0.1:8000` with auto-reload.
5. Starts the frontend on `http://127.0.0.1:3000`.

Then open **http://127.0.0.1:3000** in your browser.

If `dev.sh` is not executable, run `chmod +x dev.sh` once.

**Stop the app:** press `Ctrl+C` in the terminal where `dev.sh` runs. If it was started in the background, run:

```bash
pkill -f "uvicorn app.main:app"; pkill -f "next dev --hostname 127.0.0.1"
```

---

## 3. Daily use

Work through these screens in order.

### Bank accounts & imports
Each bank account has its own section.

- **Add bank account:** choose the bank from the list, give the account a name (for example "HDFC Salary"), and enter the last 4 digits of the account number. Only those 4 digits are stored.
- **Statements by month:** each account shows a tile for every month of the financial year: **Complete**, **Up to date** (the current month, imported up to yesterday), **Till dd/mm** (partly covered), **Missing** or **Upcoming**. Missing and partial months have an **Add statement** button; the current month has **Add newer**, for example to add statements after 10 Nov.
- **Add statements:** drop files onto the box, or click it to choose. Several files at once are fine, one per month or any date range, as CSV, XLS, XLSX or PDF. They import one by one, each with its own result. Days already imported are skipped, so overlapping statements are safe. One PDF password box applies to all PDFs in the batch.
- **Continuity check:** each new statement's opening balance must equal the last balance already stored before it. If it doesn't, the file still imports but is marked **check gap**, because transactions between the two statements may be missing.
- **Statement period:** the period printed on the statement (for example "01 Apr 2026 - 10 Nov 2026") is used for coverage, so days without transactions still count as covered.
- **Wrong-account guard:** if the statement's account number ends in different digits from the chosen account, the upload stops. You can switch to the right account or, if you are sure, import anyway.
- **Transfers between your own accounts:** a debit in one account and the same amount credited to another within 3 days is suggested as "Transfer – own account" on both sides, so it is not counted as spending or income. Use **Find transfers between my accounts** to re-run this after importing older statements.
- **Edit account** changes its name, bank or last 4 digits. An account can be removed only while it has no statements.

- **PDF password:** if the PDF is locked, a password box appears. The password is used once to open the file and is never saved or logged.
- **Reconciliation:** every row is checked. Previous balance + credit − debit must equal the printed balance. Each import shows one of these statuses:
  - **Reconciled**: all rows check out.
  - **Reconciled (reordered)**: same-day rows were out of order, and reordering fixed the check.
  - **Not verifiable**: the file has no running balance.
  - **Accepted with override**: the check failed, and you accepted the file with a written reason. The reason is kept in the CA pack.
- **Re-check:** for any override or unverifiable import, the Re-check button re-reads the stored file with the current parser. Use it after the parser has been fixed.
- **Duplicates:** the same file cannot be imported twice. Overlapping statements are fine, because rows already imported are skipped.
- **Spend summary:** right after an upload, a panel shows where the money went and the risk score for that statement. Any past import can be reopened with **Spend summary**.

### Bank account dropdown
The sidebar has a **Bank account** dropdown under the financial year: **All accounts** or any single account. Dashboard, Spend, Review, Transactions and People all follow it. With All accounts selected, each transaction shows which account it belongs to, and the closing balance is the sum of every account's latest balance.

The **Tax estimate** and the **CA pack** always cover all accounts, because tax is worked out per person, not per account. The CA pack's transaction sheet has an Account column.

### Spend
Full spend analysis for the financial year:

- **Spending risk score** (0–100) with a level: Low, Moderate, High or Critical.
- **Risk signals**, each marked OK, Watch or Danger with the reason:
  - spending compared with new money in
  - cushion left (closing balance ÷ monthly spending)
  - days the balance was near zero
  - borrowing and EMIs
  - money sent to brokers that was not returned
  - spending trend against earlier months
  - bounce and penalty charges
  - cash withdrawals
- **Spending by category**, **spending by month**, **who you paid most**, and **biggest single spends**.
- **Moved, not spent:** own-account transfers, investments, trading deposits and tax payments. These are not counted as spending.
- **Two-way money:** people who both paid you and received money from you. Money going back and forth is usually loans, splits or your own money, so it is not treated as spending.

These figures are a reading of your bank data, not financial advice. Most spending is uncategorised until you confirm it in Review, so confirm categories to sharpen the picture.

### People
Separate ledgers for people money goes back and forth with, such as Hrishikesh Reddy.

- **Track a person:** give a name and the text the bank always prints for them. Banks cut names short ("Mr Hrishik", "Hrishikesh Redd"), so a short first-name fragment such as `hrishi` usually works best. The **Suggested** list shows people who both paid you and were paid by you, and **Track** adds one in a click.
- **Ledger:** shows totals received and sent, the net ("in your favour" or "out of pocket"), a month-by-month chart, and every transaction with a running net.
- **Say what this money was:** pick one category for all money received and one for all money sent. For example, "Loan repaid to me" and "Loan given / money lent". Every row in that direction is then confirmed.
- **Kept separate:** tracked people's transactions are excluded from spending and money-in totals on the Spend page, and listed under **Tracked people** instead.
- Pinned people appear in the sidebar under People, with their net amount.
- **Remove** stops tracking. The transactions themselves are never changed.

### Review
Confirm what each credit and debit was.

- Credits and debits are shown on separate tabs.
- **Confirm** saves the category and any note for your CA.
- **Always for …** turns the decision into a rule, so future transactions from the same payee are suggested automatically.
- **Explain** on a flag and save it to resolve the flag.
- **Suggest with local AI** asks the optional local model for suggestions. Suggestions always need your confirmation.
- Keyboard: `j` and `k` move between cards, `Enter` confirms the focused card.

Only **confirmed** credits count towards income in the tax estimate and the dashboard. Suggested items are shown separately.

### Transactions
Every bank entry for the year, newest first, grouped by month with in/out totals for each month.

- Each row shows **who** (the payee name taken from the narration) in bold, with the exact bank narration below it in small grey text.
- One signed **Amount** column: green `+` for money in, `−` for money out.
- Filters: All / Money in / Money out, search, status (**Needs review** or **Confirmed**), category, person, and **Flagged only**. The totals cards above the table follow the filters.
- Change a category from the dropdown; the dot under it shows whether it is confirmed, suggested by a rule, or not categorised.
- Tracked people get a green tag that links to their ledger.

### Tax estimate
Enter Form 16 figures, TDS, advance tax, broker P&L, freelance expenses and deductions. The estimate updates about one second after you stop typing.

- Both regimes are shown side by side, with the recommended one marked.
- Each line states its source.
- Unconfirmed credits are excluded, and the estimate says how much they total.

### CA pack
Download the Excel workbook (one sheet per topic, including the original bank narration beside each classification) and the PDF summary.

### Rules
View, add, edit, disable and delete categorisation rules. Lower priority numbers run first. **Re-run on unconfirmed** re-applies the rules; it never changes anything you have confirmed.

### Settings
- Anomaly thresholds, such as the large-credit amount.
- Local AI on or off, with its model and URL. The URL must point to this computer.
- Categories: add your own, and choose each one's tax treatment.
- **Back up now** copies the database and uploads to `data/backups/` or a folder you choose.

---

## 4. Where the data lives

Everything is under `data/` in the project folder. Git ignores this folder.

| Path | Contents |
|---|---|
| `data/fintrack.db` | SQLite database: transactions, classifications, rules, tax inputs, audit log |
| `data/uploads/` | The original statement files, kept as evidence. Names begin with a SHA-256 prefix. |
| `data/exports/` | Excel and PDF CA packs |
| `data/backups/` | Backups from **Back up now** |

To keep data elsewhere, set `FINTRACK_DATA_DIR` before starting:

```bash
FINTRACK_DATA_DIR="$HOME/Documents/FinTrackData" ./dev.sh
```

Security notes:

- Turn on **FileVault** (System Settings → Privacy & Security). The data is not encrypted on disk without it. `dev.sh` warns you if it is off.
- The backend listens only on `127.0.0.1`. Other computers on your network cannot reach it.
- Every write request must carry the `X-FinTrack` header. This blocks cross-site requests from other websites.
- Never commit `data/` or a real statement to git.

---

## 5. Optional: local AI suggestions (free)

1. Install [Ollama](https://ollama.com) and open it once.
2. In a terminal, run `ollama pull qwen2.5:7b`.
3. In FinTrack, go to **Settings → Local AI**, tick **Enabled**, and save.
4. On the Review page, click **Suggest with local AI**.

Everything runs on your computer. Without Ollama, the rules still work, and you categorise by hand.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| "Backend not running" screen | The backend did not start. Check the terminal running `dev.sh` for errors. Run `./dev.sh` again. |
| Port 8000 or 3000 already in use | An older copy is still running. Stop it (see section 2), then start again. |
| `pnpm: command not found` | Install pnpm (`brew install pnpm`). |
| Python version error | Install Python 3.12 (`brew install python@3.12`) and delete `backend/.venv`, then run `./dev.sh` again. |
| "Could not find the transaction table header" | The file is not a recognised Kotak layout. Try the Excel or CSV download instead of the PDF. |
| "The statement did not reconcile" | A row is missing or misread. Try another format. If you have checked the statement, you can accept it with a reason. Once the parser is fixed, use **Re-check**. |
| "This PDF is password-protected" | Enter the statement password in the box that appears. |
| "This exact file was already imported" | Nothing to do. The statement is already in the database. |
| Local AI: "Could not reach Ollama" | Start Ollama, and check that the URL in Settings is `http://127.0.0.1:11434`. |
| Dashboard shows gaps | A period in the financial year has no statement. Import it; the gap disappears. |

To reset everything and start empty, stop the app and delete the `data/` folder. This cannot be undone. Make a backup first.

---

## 7. Limits (read before relying on it)

- **The tax figure is an estimate.** Confirm it with your CA before filing.
- **FY 2026-27 tax rules are unverified.** They are copied from FY 2025-26 (`backend/app/tax/rules/2026-27.yaml`, marked `verified: false`). Check them against Finance Act 2026 and the Income-tax Act 2025. The app shows a warning while they are unverified.
- **Not modelled in the tax estimate:**
  - loss carry-forward
  - surcharge marginal relief
  - senior-citizen slabs
  - house-property income other than home-loan interest
- **The spending risk score is a heuristic.** It reads patterns in the data. It does not know your goals, your obligations outside this account, or cash you spend without this account.
- **Bank formats:** one parser handles every bank by finding columns by name (Date / Narration or Description / Withdrawal / Deposit / Balance). It was tested on one real Kotak PDF and on synthetic Kotak and HDFC files. A real HDFC, ICICI, SBI or Axis statement may need small adjustments; if one fails, try the Excel or CSV download.
- **Phase 2, not built yet:** AIS and Form 26AS reconciliation, broker P&L import, document vault, and a business/LLP profile.

---

## 8. Development

```bash
cd backend && .venv/bin/python -m pytest -q        # backend tests (41)
cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src
cd frontend && pnpm exec next build                # production build check
```

Project layout:

```
dev.sh                  start script
backend/app/            FastAPI app
  banks.py              supported banks and parser selection
  importers/            statement parser (header-based, all banks) and balance reconciliation
  transfers.py          matching transfers between your own accounts
  tax/engine.py         tax computation
  tax/rules/*.yaml      tax rules per financial year
  classify.py           rules engine, counterparty extraction, local AI
  spend.py              spend analytics and risk score
  people.py             tracked-people ledgers and suggestions
  reports.py            Excel and PDF CA pack
  seed.py               default categories and built-in rules
backend/tests/          test suite
frontend/src/app/       pages (dashboard, spend, review, transactions, people, imports, tax, reports, rules, settings)
frontend/src/components shared UI and spend components
docs/superpowers/specs/ design document
```

The design document is at `docs/superpowers/specs/2026-11-11-fintrack-design.md`. Some parts of it describe the original plan; this README is the accurate description of what is built.
