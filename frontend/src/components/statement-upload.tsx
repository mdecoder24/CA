"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { monthTitle } from "@/components/month-strip";
import { useApp } from "@/components/shell";
import { type Account, api, ApiError, type Continuity, fmtDate, type ImportBatch, type MonthCoverage } from "@/lib/api";

/* ------------------------------------------------------------------ month calendar */

const STATE = {
  full: { icon: "✓", cls: "border-line bg-surface", badge: "chip chip-ok" },
  partial: { icon: "◐", cls: "border-warn/50 bg-warn-soft", badge: "chip chip-warn" },
  missing: { icon: "○", cls: "border-line bg-surface", badge: "chip chip-danger" },
  upcoming: { icon: "·", cls: "border-line border-dashed bg-transparent opacity-60", badge: "chip" },
} as const;

function label(c: MonthCoverage) {
  if (c.status === "full") return c.in_progress ? `Up to date` : "Complete";
  if (c.status === "partial") return c.covered_until ? `Till ${fmtDate(c.covered_until).slice(0, 5)}` : "Partly";
  if (c.status === "missing") return "Missing";
  return "Upcoming";
}

export function MonthCalendar({ months, onAdd }: { months: MonthCoverage[]; onAdd: (m: MonthCoverage) => void }) {
  const full = months.filter((m) => m.status === "full").length;
  const due = months.filter((m) => m.status !== "upcoming").length;
  return (
    <section className="card mt-4 p-4 md:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold">Statements by month</h3>
        <span className="text-ink-3 text-[12.5px]">
          {full} of {due} months covered
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {months.map((m) => {
          const st = STATE[m.status];
          const needs = m.status === "missing" || m.status === "partial";
          return (
            <div key={m.month} className={`rounded-lg border p-3 ${st.cls}`}>
              <div className="text-[13.5px] font-semibold whitespace-nowrap">{monthTitle(m.month, "short")}</div>
              <span className={`${st.badge} mt-1.5`}>
                <span aria-hidden>{st.icon}</span>
                {label(m)}
              </span>
              <div className="text-ink-3 mt-1.5 text-[11.5px]">
                {m.status === "upcoming" ? "Not yet" : `${m.txn_count} transactions`}
              </div>
              {needs && (
                <button className="btn btn-sm mt-2 w-full" onClick={() => onAdd(m)}>
                  Add statement
                </button>
              )}
              {m.status === "full" && m.in_progress && (
                <button className="btn btn-ghost btn-sm mt-2 w-full" onClick={() => onAdd(m)}>
                  Add newer
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ multi-file upload */

type Item = {
  key: string;
  file: File;
  state: "queued" | "uploading" | "done" | "error" | "reconcile" | "mismatch" | "password";
  message?: string;
  inserted?: number;
  duplicates?: number;
  continuity?: Continuity;
  batch?: ImportBatch;
  reason?: string;
};

export type UploaderHandle = { focus: (hint: string) => void };

export const StatementUploader = forwardRef<
  UploaderHandle,
  { account: Account; others: Account[]; onImported: (b: ImportBatch) => void; onPick: (id: number) => void }
>(function StatementUploader({ account, others, onImported, onPick }, ref) {
  const { toast } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const zoneRef = useRef<HTMLLabelElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [hint, setHint] = useState("");

  useImperativeHandle(ref, () => ({
    focus(h: string) {
      setHint(h);
      zoneRef.current?.scrollIntoView({ block: "center" });
      inputRef.current?.focus();
    },
  }));

  const patch = (key: string, p: Partial<Item>) => setItems((list) => list.map((i) => (i.key === key ? { ...i, ...p } : i)));

  const add = (files: FileList | File[]) => {
    const ok = [...files].filter((f) => /\.(csv|xls|xlsx|pdf)$/i.test(f.name));
    if (ok.length < [...files].length) toast("Only CSV, XLS, XLSX and PDF files can be imported.", "error");
    // Oldest first by name helps continuity checks when files are named by month.
    ok.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    setItems((list) => [
      ...list.filter((i) => i.state !== "done"),
      ...ok.map((file) => ({ key: `${file.name}-${file.size}-${file.lastModified}`, file, state: "queued" as const })),
    ]);
  };

  const uploadOne = async (it: Item, opts: { override?: string; force?: boolean } = {}) => {
    patch(it.key, { state: "uploading", message: undefined });
    const form = new FormData();
    form.append("file", it.file);
    form.append("account_id", String(account.id));
    if (password) form.append("password", password);
    if (opts.override) form.append("override_reason", opts.override);
    if (opts.force) form.append("force_account", "true");
    try {
      const r = await api.upload<{ inserted: number; duplicates: number; batch: ImportBatch; continuity: Continuity }>("/api/imports", form);
      patch(it.key, { state: "done", inserted: r.inserted, duplicates: r.duplicates, continuity: r.continuity, batch: r.batch });
      onImported(r.batch);
      return true;
    } catch (e) {
      const err = e as ApiError;
      const state =
        err.code === "password_required"
          ? "password"
          : err.code === "reconcile_failed"
            ? "reconcile"
            : err.code === "account_mismatch"
              ? "mismatch"
              : "error";
      patch(it.key, { state, message: err.message });
      return false;
    }
  };

  const runAll = async () => {
    setBusy(true);
    let done = 0;
    for (const it of items) {
      if (it.state === "queued" || it.state === "password" || it.state === "error") {
        if (await uploadOne(it)) done++;
      }
    }
    setBusy(false);
    if (done) toast(`Imported ${done} statement${done > 1 ? "s" : ""} into ${account.nickname}.`);
  };

  const pending = items.filter((i) => ["queued", "password", "error"].includes(i.state)).length;
  const needsPassword = items.some((i) => i.state === "password") || items.some((i) => /\.pdf$/i.test(i.file.name) && i.state !== "done");

  return (
    <div className="mt-4">
      {hint && <div className="bg-accent-soft text-accent mb-3 rounded-lg px-3 py-2 text-[13px] font-medium">{hint}</div>}

      <label
        ref={zoneRef}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          add(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-7 text-center ${
          drag ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2"
        }`}
      >
        <span className="text-[14.5px] font-semibold">Drop statements here, or click to choose</span>
        <span className="text-ink-3 text-[12.5px]">
          One file per month or any date range · several at once · CSV, Excel or PDF · already-imported days are skipped
        </span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.xls,.xlsx,.pdf"
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) add(e.target.files);
            e.target.value = "";
          }}
        />
      </label>

      {items.length > 0 && (
        <div className="mt-3 space-y-2">
          {items.map((it) => (
            <FileRow
              key={it.key}
              it={it}
              others={others}
              onPick={onPick}
              onRemove={() => setItems((l) => l.filter((x) => x.key !== it.key))}
              onReason={(reason) => patch(it.key, { reason })}
              onOverride={() => uploadOne(it, { override: it.reason })}
              onForce={() => uploadOne(it, { force: true })}
            />
          ))}
          <div className="flex flex-wrap items-end gap-3 pt-1">
            {needsPassword && (
              <label className="flex w-full flex-col gap-1 sm:w-60">
                <span className="label">PDF password (used for all PDFs here)</span>
                <input type="password" autoComplete="off" className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
              </label>
            )}
            <button className="btn btn-primary" onClick={runAll} disabled={!pending || busy}>
              {busy ? "Importing…" : `Import ${pending} file${pending === 1 ? "" : "s"}`}
            </button>
            {items.some((i) => i.state === "done") && (
              <button className="btn btn-ghost" onClick={() => setItems((l) => l.filter((i) => i.state !== "done"))}>
                Clear finished
              </button>
            )}
          </div>
        </div>
      )}
      <p className="text-ink-3 mt-3 text-[12px]">
        Each statement is checked row by row (previous balance + credit − debit = printed balance), and its opening balance must continue from the
        last balance already stored. A PDF password is used once and never saved.
      </p>
    </div>
  );
});

function FileRow({
  it,
  others,
  onPick,
  onRemove,
  onReason,
  onOverride,
  onForce,
}: {
  it: Item;
  others: Account[];
  onPick: (id: number) => void;
  onRemove: () => void;
  onReason: (r: string) => void;
  onOverride: () => void;
  onForce: () => void;
}) {
  const tone =
    it.state === "done"
      ? it.continuity && !it.continuity.ok
        ? "chip chip-warn"
        : "chip chip-ok"
      : it.state === "uploading" || it.state === "queued"
        ? "chip"
        : "chip chip-danger";
  const text = {
    queued: "Waiting",
    uploading: "Importing…",
    done: it.continuity && !it.continuity.ok ? "Imported · check gap" : "Imported",
    error: "Failed",
    reconcile: "Didn't reconcile",
    mismatch: "Different account?",
    password: "Needs password",
  }[it.state];

  return (
    <div className="border-line rounded-lg border px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-medium">{it.file.name}</div>
          {it.state === "done" && it.batch && (
            <div className="text-ink-3 text-[12px]">
              {fmtDate(it.batch.period_from)} – {fmtDate(it.batch.period_to)} · {it.inserted} new
              {it.duplicates ? `, ${it.duplicates} already there` : ""}
              {it.batch.period_from && <> · {monthTitle(it.batch.period_from.slice(0, 7), "short")}</>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={tone}>{text}</span>
          {it.state !== "uploading" && it.state !== "done" && (
            <button className="btn btn-ghost btn-sm" onClick={onRemove} aria-label={`Remove ${it.file.name}`}>
              Remove
            </button>
          )}
        </div>
      </div>
      {it.message && it.state !== "done" && <p className="text-ink-2 mt-1.5 text-[12.5px]">{it.message}</p>}
      {it.state === "done" && it.continuity && !it.continuity.ok && <p className="text-warn mt-1.5 text-[12.5px]">{it.continuity.message}</p>}
      {it.state === "reconcile" && (
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            className="input min-w-0 flex-1"
            placeholder="If you've checked the statement, say why to import it anyway (goes into the CA pack)"
            value={it.reason ?? ""}
            onChange={(e) => onReason(e.target.value)}
          />
          <button className="btn btn-sm self-center" disabled={(it.reason ?? "").trim().length < 10} onClick={onOverride}>
            Import anyway
          </button>
        </div>
      )}
      {it.state === "mismatch" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {others.map((o) => (
            <button key={o.id} className="btn btn-sm" onClick={() => onPick(o.id)}>
              Switch to {o.nickname}
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={onForce}>
            It is this account, import anyway
          </button>
        </div>
      )}
    </div>
  );
}
