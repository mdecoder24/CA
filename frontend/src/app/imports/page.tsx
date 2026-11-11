"use client";

import { useRef, useState } from "react";
import { PageHeader, useApp } from "@/components/shell";
import { type Spend, SpendSnapshot } from "@/components/spend-report";
import { type Account, api, ApiError, type Bank, fmtDate, type ImportBatch, paise } from "@/lib/api";
import { useData } from "@/lib/use-data";

const STATUS: Record<string, { text: string; cls: string }> = {
  ok: { text: "Reconciled", cls: "chip-ok" },
  reordered: { text: "Reconciled (reordered)", cls: "chip-ok" },
  unchecked: { text: "Not verifiable", cls: "chip-warn" },
  override: { text: "Accepted with override", cls: "chip-danger" },
};

const initials = (name: string) =>
  name
    .replace(/bank|ltd\.?|limited/gi, "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase() || "?";

export default function ImportsPage() {
  const { accounts, accountId, setAccountId, toast, bump } = useApp();
  const { data: banks } = useData(() => api.get<Bank[]>("/api/banks"), []);
  const [picked, setPicked] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [snapshot, setSnapshot] = useState<Spend | null>(null);

  // Selected section: what you clicked, else the sidebar account, else the first account.
  const selected =
    accounts.find((a) => a.id === picked) ?? accounts.find((a) => String(a.id) === accountId) ?? accounts[0] ?? null;

  const matchTransfers = async () => {
    try {
      const r = await api.send<{ matched: number }>("POST", "/api/accounts/match-transfers");
      toast(r.matched ? `Found ${r.matched} transfers between your accounts. They are suggested as own-account transfers.` : "No new transfers between your accounts found.");
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <>
      <PageHeader
        title="Bank accounts & imports"
        sub="Add each bank account once, then upload its statements into its own section. Excel, CSV or PDF; overlapping statements are fine."
        actions={
          accounts.length > 1 ? (
            <button className="btn" onClick={matchTransfers}>
              Find transfers between my accounts
            </button>
          ) : undefined
        }
      />

      {/* Accounts */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {accounts.map((a) => {
          const active = selected?.id === a.id;
          return (
            <button
              key={a.id}
              onClick={() => {
                setPicked(a.id);
                setSnapshot(null);
              }}
              className={`month-chip card flex items-start gap-3 p-4 text-left ${active ? "border-accent ring-accent ring-1" : "hover:bg-surface-2"}`}
              aria-pressed={active}
            >
              <span
                className={`flex size-10 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold ${
                  active ? "bg-accent text-bg" : "bg-surface-2 text-ink-2"
                }`}
                aria-hidden
              >
                {initials(a.bank_name)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold">{a.nickname}</span>
                <span className="text-ink-3 block truncate text-[12px]">
                  {a.bank_name}
                  {a.masked_number && ` · ••${a.masked_number.slice(-4)}`}
                </span>
                <span className="num mt-2 block text-[16px] font-semibold">{a.balance !== null ? paise(a.balance, true) : "—"}</span>
                <span className="text-ink-3 block text-[11.5px]">
                  {a.txn_count ? `${a.txn_count} transactions · up to ${fmtDate(a.last_date)}` : "No statements yet"}
                </span>
              </span>
            </button>
          );
        })}
        <button
          onClick={() => setAdding((v) => !v)}
          className={`month-chip border-line text-ink-2 hover:bg-surface-2 flex min-h-[92px] items-center justify-center gap-2 rounded-xl border border-dashed p-4 text-[13.5px] font-medium ${
            adding ? "bg-surface-2" : ""
          }`}
        >
          <span aria-hidden className="text-[18px] leading-none">
            +
          </span>
          {adding ? "Cancel" : "Add bank account"}
        </button>
      </div>

      {adding && (
        <AddAccount
          banks={banks ?? []}
          onAdded={(a) => {
            setAdding(false);
            setPicked(a.id);
            setAccountId(String(a.id));
            bump();
            toast(`${a.nickname} added. Upload its statements below.`);
          }}
        />
      )}

      {selected && (
        <AccountSection
          key={selected.id}
          account={selected}
          banks={banks ?? []}
          others={accounts.filter((a) => a.id !== selected.id)}
          onImported={(batch) => {
            bump();
            api
              .get<Spend>("/api/spend", { batch_id: batch.id })
              .then(setSnapshot)
              .catch(() => setSnapshot(null));
          }}
          onSnapshot={setSnapshot}
          snapshot={snapshot}
          onPick={(id) => setPicked(id)}
        />
      )}
    </>
  );
}

function AddAccount({ banks, onAdded }: { banks: Bank[]; onAdded: (a: Account) => void }) {
  const { toast } = useApp();
  const [bank, setBank] = useState("");
  const [nickname, setNickname] = useState("");
  const [last4, setLast4] = useState("");
  return (
    <form
      className="card mt-3 grid gap-3 p-4 md:grid-cols-[1.2fr_1fr_140px_auto] md:items-end"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          onAdded(await api.send<Account>("POST", "/api/accounts", { bank, nickname, last4 }));
        } catch (err) {
          toast((err as Error).message, "error");
        }
      }}
    >
      <label className="flex flex-col gap-1">
        <span className="label">Bank</span>
        <select className="select" value={bank} onChange={(e) => setBank(e.target.value)} autoFocus>
          <option value="" disabled>
            Choose your bank…
          </option>
          {banks.map((b) => (
            <option key={b.code} value={b.code}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="label">Name for this account</span>
        <input className="input" value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder="e.g. HDFC Salary" />
      </label>
      <label className="flex flex-col gap-1">
        <span className="label">Last 4 digits</span>
        <input
          className="input num"
          inputMode="numeric"
          maxLength={4}
          value={last4}
          onChange={(e) => setLast4(e.target.value.replace(/\D/g, ""))}
          placeholder="1234"
        />
      </label>
      <button className="btn btn-primary" disabled={!bank}>
        Add account
      </button>
      <p className="text-ink-3 text-[12px] md:col-span-4">
        The last 4 digits let FinTrack stop you from uploading a statement into the wrong account. Only these 4 digits are stored, never the full number.
      </p>
    </form>
  );
}

function AccountSection({
  account,
  banks,
  others,
  onImported,
  onSnapshot,
  snapshot,
  onPick,
}: {
  account: Account;
  banks: Bank[];
  others: Account[];
  onImported: (b: ImportBatch) => void;
  onSnapshot: (s: Spend | null) => void;
  snapshot: Spend | null;
  onPick: (id: number) => void;
}) {
  const { toast, bump } = useApp();
  const { data: batches } = useData(() => api.get<ImportBatch[]>("/api/imports", { account_id: account.id }), [account.id]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [needPassword, setNeedPassword] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [mismatch, setMismatch] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const reset = () => {
    setFile(null);
    setPassword("");
    setNeedPassword(false);
    setFailure(null);
    setMismatch(null);
    setReason("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async (opts: { override?: boolean; force?: boolean } = {}) => {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", String(account.id));
    if (password) form.append("password", password);
    if (opts.override) form.append("override_reason", reason);
    if (opts.force) form.append("force_account", "true");
    try {
      const r = await api.upload<{ inserted: number; duplicates: number; batch: ImportBatch }>("/api/imports", form);
      toast(`Imported ${r.inserted} transactions into ${account.nickname}${r.duplicates ? `, skipped ${r.duplicates} already imported` : ""}.`);
      reset();
      onImported(r.batch);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "password_required") {
        setNeedPassword(true);
        toast(err.message, "error");
      } else if (err.code === "reconcile_failed") {
        setFailure(err.message);
      } else if (err.code === "account_mismatch") {
        setMismatch(err.message);
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
      <section className="card mt-4 p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold tracking-tight">Upload a {account.bank_name} statement</h2>
            <p className="text-ink-3 text-[12.5px]">
              Goes into <b className="text-ink-2">{account.nickname}</b>
              {account.masked_number && <> ({account.masked_number})</>}.
            </p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close" : "Edit account"}
          </button>
        </div>

        {editing && (
          <EditAccount
            account={account}
            banks={banks}
            onDone={() => {
              setEditing(false);
              bump();
            }}
          />
        )}

        <form
          className="mt-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
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
                setMismatch(null);
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
          Every row is checked: previous balance + credit − debit must equal the printed balance. A PDF password is used once to open the file and is never saved.
        </p>

        {mismatch && (
          <div className="bg-warn-soft mt-4 rounded-lg p-4">
            <div className="text-warn text-[13.5px] font-semibold">This looks like a different account</div>
            <p className="mt-1 text-[13.5px]">{mismatch}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {others.map((o) => (
                <button key={o.id} className="btn btn-sm" onClick={() => onPick(o.id)}>
                  Switch to {o.nickname}
                </button>
              ))}
              <button className="btn btn-ghost btn-sm" onClick={() => submit({ force: true })} disabled={busy}>
                It is this account, import anyway
              </button>
            </div>
          </div>
        )}

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
              <button className="btn" onClick={() => submit({ override: true })} disabled={reason.trim().length < 10 || busy}>
                Import anyway
              </button>
              <button className="btn btn-ghost" onClick={reset}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      {snapshot && <SpendSnapshot d={snapshot} onClose={() => onSnapshot(null)} />}

      <section className="card mt-4 overflow-hidden">
        <h3 className="border-line border-b px-4 py-3 text-[14px] font-semibold">Statements imported into {account.nickname}</h3>
        <div className="overflow-x-auto">
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
                    No statements yet for this account.
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
                                onSnapshot(d);
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
        </div>
      </section>
    </>
  );
}

function EditAccount({ account, banks, onDone }: { account: Account; banks: Bank[]; onDone: () => void }) {
  const { toast, setAccountId } = useApp();
  const [bank, setBank] = useState(account.bank);
  const [nickname, setNickname] = useState(account.nickname);
  const [last4, setLast4] = useState(account.masked_number.slice(-4));
  const [confirmRemove, setConfirmRemove] = useState(false);
  return (
    <form
      className="border-line mt-3 grid gap-3 border-t pt-3 md:grid-cols-[1.2fr_1fr_140px_auto] md:items-end"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.send("PUT", `/api/accounts/${account.id}`, { bank, nickname, last4 });
          toast("Account saved.");
          onDone();
        } catch (err) {
          toast((err as Error).message, "error");
        }
      }}
    >
      <label className="flex flex-col gap-1">
        <span className="label">Bank</span>
        <select className="select" value={bank} onChange={(e) => setBank(e.target.value)}>
          {banks.map((b) => (
            <option key={b.code} value={b.code}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="label">Name</span>
        <input className="input" value={nickname} onChange={(e) => setNickname(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="label">Last 4 digits</span>
        <input className="input num" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, ""))} />
      </label>
      <div className="flex gap-2">
        <button className="btn btn-primary btn-sm">Save</button>
        {account.imports === 0 &&
          (confirmRemove ? (
            <button
              type="button"
              className="btn btn-sm text-danger"
              onClick={async () => {
                try {
                  await api.send("DELETE", `/api/accounts/${account.id}`);
                  toast(`${account.nickname} removed.`);
                  setAccountId("");
                  onDone();
                } catch (err) {
                  toast((err as Error).message, "error");
                }
              }}
            >
              Confirm remove
            </button>
          ) : (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmRemove(true)}>
              Remove
            </button>
          ))}
      </div>
    </form>
  );
}
