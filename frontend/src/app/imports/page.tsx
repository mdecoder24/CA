"use client";

import { useRef, useState } from "react";
import { PageHeader, useApp } from "@/components/shell";
import { type Spend, SpendSnapshot } from "@/components/spend-report";
import { api, ApiError, fmtDate, type ImportBatch, paise } from "@/lib/api";
import { useData } from "@/lib/use-data";

const STATUS: Record<string, { text: string; cls: string }> = {
  ok: { text: "Reconciled", cls: "chip-ok" },
  reordered: { text: "Reconciled (reordered)", cls: "chip-ok" },
  unchecked: { text: "Not verifiable", cls: "chip-warn" },
  override: { text: "Accepted with override", cls: "chip-danger" },
};

export default function ImportsPage() {
  const { toast, bump } = useApp();
  const { data: batches } = useData(() => api.get<ImportBatch[]>("/api/imports"), []);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [needPassword, setNeedPassword] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [snapshot, setSnapshot] = useState<Spend | null>(null);

  const reset = () => {
    setFile(null);
    setPassword("");
    setNeedPassword(false);
    setFailure(null);
    setReason("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async (withOverride = false) => {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", "1");
    if (password) form.append("password", password);
    if (withOverride) form.append("override_reason", reason);
    try {
      const r = await api.upload<{ inserted: number; duplicates: number; batch: ImportBatch }>("/api/imports", form);
      toast(`Imported ${r.inserted} transactions${r.duplicates ? `, skipped ${r.duplicates} already imported` : ""}.`);
      reset();
      bump();
      api
        .get<Spend>("/api/spend", { batch_id: r.batch.id })
        .then(setSnapshot)
        .catch(() => setSnapshot(null));
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "password_required") {
        setNeedPassword(true);
        toast(err.message, "error");
      } else if (err.code === "reconcile_failed") {
        setFailure(err.message);
      } else {
        toast(err.message, "error");
      }
    } finally {
      setBusy(false);
      setPassword("");
    }
  };

  return (
    <>
      <PageHeader title="Imports" sub="Upload Kotak statements: Excel, CSV or PDF. Overlapping statements are fine; repeated rows are skipped." />

      <section className="card p-4 md:p-5">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit(false);
          }}
        >
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="label">Statement file</span>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xls,.xlsx,.pdf"
              className="input py-1.5"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setFailure(null);
                setNeedPassword(false);
              }}
            />
          </label>
          {(needPassword || file?.name.toLowerCase().endsWith(".pdf")) && (
            <label className="flex w-full flex-col gap-1 sm:w-56">
              <span className="label">PDF password {needPassword ? "(required)" : "(if any)"}</span>
              <input
                type="password"
                autoComplete="off"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus={needPassword}
              />
            </label>
          )}
          <button type="submit" className="btn btn-primary" disabled={!file || busy}>
            {busy ? "Importing…" : "Import"}
          </button>
        </form>
        <p className="text-ink-3 mt-3 text-[12px]">
          Every row is checked: previous balance + credit − debit must equal the printed balance. The password is used once to open the file and is never saved.
        </p>

        {failure && (
          <div className="bg-danger-soft mt-4 rounded-lg p-4">
            <div className="text-danger text-[13.5px] font-semibold">The statement did not reconcile</div>
            <p className="mt-1 text-[13.5px]">{failure}</p>
            <p className="text-ink-2 mt-2 text-[12.5px]">
              Usually this means the file is incomplete or was read wrongly. Try another format (Excel instead of PDF). If you have checked the statement and want to import it anyway, write why. The reason goes into the audit trail and the CA pack.
            </p>
            <textarea
              className="input mt-2 h-20 w-full py-2"
              placeholder="e.g. Checked against passbook; the bank printed a wrong balance on 12-07."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="mt-2 flex gap-2">
              <button className="btn" onClick={() => submit(true)} disabled={reason.trim().length < 10 || busy}>
                Import anyway
              </button>
              <button className="btn btn-ghost" onClick={reset}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      {snapshot && <SpendSnapshot d={snapshot} onClose={() => setSnapshot(null)} />}

      <section className="card mt-4 overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>File</th>
              <th>Period</th>
              <th className="text-right">Rows</th>
              <th className="text-right">Closing</th>
              <th>Check</th>
              <th>Imported</th>
            </tr>
          </thead>
          <tbody>
            {batches?.length === 0 && (
              <tr>
                <td colSpan={6} className="text-ink-3 py-8 text-center">
                  No statements imported yet.
                </td>
              </tr>
            )}
            {batches?.map((b) => {
              const s = STATUS[b.status] ?? { text: b.status, cls: "" };
              return (
                <tr key={b.id}>
                  <td className="max-w-64">
                    <div className="truncate font-medium" title={b.filename}>
                      {b.filename}
                    </div>
                    <div className="text-ink-3 font-mono text-[11px]" title={b.sha256}>
                      {b.sha256.slice(0, 12)}
                    </div>
                  </td>
                  <td className="num">
                    {fmtDate(b.period_from)} – {fmtDate(b.period_to)}
                  </td>
                  <td className="num text-right">
                    {b.rows_inserted}
                    {b.rows_duplicate > 0 && <div className="text-ink-3 text-[11.5px]">{b.rows_duplicate} skipped</div>}
                  </td>
                  <td className="num text-right">{paise(b.closing_balance)}</td>
                  <td>
                    <span className={`chip ${s.cls}`} title={b.reconcile_detail}>
                      {s.text}
                    </span>
                    {b.override_reason && <div className="text-ink-2 mt-1 max-w-56 text-[12px]">“{b.override_reason}”</div>}
                    {(b.status === "override" || b.status === "unchecked") && (
                      <button
                        className="btn btn-sm mt-1.5"
                        onClick={async () => {
                          try {
                            const r = await api.upload<ImportBatch>(`/api/imports/${b.id}/recheck`, new FormData());
                            toast(r.status === "override" ? "Still does not reconcile." : "Re-checked: statement reconciles.");
                            bump();
                          } catch (e) {
                            toast((e as Error).message, "error");
                          }
                        }}
                      >
                        Re-check
                      </button>
                    )}
                  </td>
                  <td className="num text-ink-2">
                    {new Date(b.created_at).toLocaleDateString("en-IN")}
                    <div>
                      <button
                        className="btn btn-ghost btn-sm -ml-2.5 mt-1"
                        onClick={() =>
                          api
                            .get<Spend>("/api/spend", { batch_id: b.id })
                            .then((d) => {
                              setSnapshot(d);
                              window.scrollTo({ top: 0 });
                            })
                            .catch((e) => toast((e as Error).message, "error"))
                        }
                      >
                        Spend summary
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
