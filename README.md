# FinTrack

FinTrack is a personal finance and tax-preparation tool for one person in India. It runs only on your own computer, and your bank data never leaves it.

You upload Kotak statements, and FinTrack does three things:

1. **Explains every credit.** Rules and an optional local AI suggest a category. You confirm each one in the Review screen. Anything unusual is flagged: large credits, cash deposits, possible duplicates, and repeated round amounts.
2. **Estimates tax** under the old and the new regime, net of TDS and advance tax. It counts **confirmed** income only. Transfers, refunds and trading capital are never counted as income.
3. **Builds a CA pack:** an Excel workbook plus a PDF summary for your Chartered Accountant.

Original bank data is stored as it is and is never edited. All classification lives in separate tables.

## Start

```bash
./dev.sh
```

Then open http://127.0.0.1:3000.

The first run creates the Python environment and installs packages. You need Python 3.11+ (`brew install python@3.12`), Node 20+ and pnpm.

## Using it

1. **Imports:** upload a Kotak statement (CSV, XLS, XLSX or PDF). For a password-protected PDF, type the password. It is used once and never saved.
   - Each row is checked: previous balance + credit − debit must equal the printed balance.
   - Overlapping statements are fine, because rows already imported are skipped.
2. **Review:** confirm each credit and add notes for your CA. Tick "Always for …" to turn a decision into a rule. Use `j`/`k` to move between cards and `Enter` to confirm.
3. **Tax estimate:** enter Form 16 figures, TDS, broker P&L and deductions. The estimate updates as you type.
4. **CA pack:** download the Excel workbook and the PDF summary.

## Data

- Everything is stored under `data/`, which git ignores: the SQLite database, the original uploads, exports and backups.
- Turn on macOS FileVault so this folder is encrypted on disk.
- Use **Settings → Back up now** to copy the database and uploads.

## Optional: local AI suggestions (free)

1. Install [Ollama](https://ollama.com).
2. Run `ollama pull qwen2.5:7b`.
3. Enable local AI in Settings.

Suggestions always need your confirmation.

## Limits (read before relying on it)

- **The tax figure is an estimate.** Confirm it with your CA before filing.
- **FY 2026-27 tax rules are unverified.** They are copied from FY 2025-26 (`backend/app/tax/rules/2026-27.yaml`, marked `verified: false`). Check them against Finance Act 2026 and the Income-tax Act 2025.
- **Not modelled:**
  - loss carry-forward
  - surcharge marginal relief
  - senior-citizen slabs
  - house-property income other than home-loan interest
- **Phase 2 (not built yet):** AIS / 26AS reconciliation, broker P&L import, document vault, business/LLP profile, and banks other than Kotak.
- **The Kotak parser was built without a real statement.** It finds columns by their names. If your file fails to import, try another format, such as Excel instead of PDF.

## Development

```bash
cd backend && .venv/bin/python -m pytest -q        # backend tests
cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src
```

The design is in `docs/superpowers/specs/2026-11-11-fintrack-design.md`.
