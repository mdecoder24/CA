"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CategorySelect, StatusChip } from "@/components/category-select";
import { monthStats, MonthStrip, monthTitle } from "@/components/month-strip";
import { Segmented } from "@/components/segmented";
import { compactInr, Empty, PageHeader, useApp } from "@/components/shell";
import { api, type Category, fmtDate, type Ledger, monthLabel, paise, type PersonSuggestion, type PersonSummary } from "@/lib/api";
import { useData } from "@/lib/use-data";

// The selected person lives in the URL hash (/people#3) so sidebar links work.
const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};
const useHashId = () =>
  useSyncExternalStore(
    subscribe,
    () => Number(window.location.hash.slice(1)) || 0,
    () => 0,
  );

export default function PeoplePage() {
  const { fy, toast, bump, accountId } = useApp();
  const hashId = useHashId();
  const { data: people, reload } = useData(() => api.get<PersonSummary[]>("/api/people", { fy, account_id: accountId }), [fy, accountId]);
  const { data: suggestions, reload: reloadSug } = useData(
    () => api.get<PersonSuggestion[]>("/api/people-suggestions", { fy, account_id: accountId }),
    [fy, accountId],
  );
  const [adding, setAdding] = useState(false);

  const selected = people?.find((p) => p.id === hashId) ?? people?.[0] ?? null;

  const track = async (name: string, pattern: string) => {
    try {
      const p = await api.send<{ id: number }>("POST", "/api/people", { name, pattern, pinned: true });
      toast(`Now tracking ${name} separately.`);
      reload();
      reloadSug();
      bump();
      window.location.hash = String(p.id);
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    }
  };

  return (
    <>
      <PageHeader
        title="People"
        sub="Separate ledgers for people money goes back and forth with. Their transactions are kept out of spending and income totals."
        actions={
          <button className="btn" onClick={() => setAdding((a) => !a)}>
            {adding ? "Cancel" : "Track a person"}
          </button>
        }
      />

      {adding && (
        <AddPerson
          onAdd={async (n, p) => {
            if (await track(n, p)) setAdding(false);
          }}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <aside className="space-y-4">
          <section className="card overflow-hidden">
            <h2 className="text-ink-3 border-line border-b px-4 py-2.5 text-[11.5px] font-semibold tracking-wide uppercase">Tracked</h2>
            {people?.length === 0 && <p className="text-ink-2 px-4 py-4 text-[13px]">No one yet. Track someone from the suggestions below.</p>}
            <ul>
              {people?.map((p) => {
                const active = selected?.id === p.id;
                return (
                  <li key={p.id}>
                    <a
                      href={`#${p.id}`}
                      className={`border-line block border-b px-4 py-3 last:border-b-0 ${active ? "bg-accent-soft" : "hover:bg-surface-2"}`}
                    >
                      <div className={`truncate text-[13.5px] font-semibold ${active ? "text-accent" : ""}`}>{p.name}</div>
                      <div className="text-ink-3 num mt-0.5 flex justify-between text-[12px]">
                        <span>{p.count} transactions</span>
                        <span className={p.net >= 0 ? "text-credit" : ""}>
                          net {p.net >= 0 ? "+" : "−"}
                          {compactInr(Math.abs(p.net))}
                        </span>
                      </div>
                    </a>
                  </li>
                );
              })}
            </ul>
          </section>

          {suggestions && suggestions.length > 0 && (
            <section className="card overflow-hidden">
              <h2 className="text-ink-3 border-line border-b px-4 py-2.5 text-[11.5px] font-semibold tracking-wide uppercase">
                Suggested
              </h2>
              <p className="text-ink-3 px-4 pt-2.5 text-[12px]">Money went both to and from these people.</p>
              <ul className="px-2 py-2">
                {suggestions.map((s) => (
                  <li key={s.key} className="hover:bg-surface-2 flex items-center justify-between gap-2 rounded-lg px-2 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium" title={s.names_seen.join(", ")}>
                        {s.name}
                      </div>
                      <div className="text-ink-3 num text-[11.5px]">
                        in {compactInr(s.received)} · out {compactInr(s.sent)}
                      </div>
                    </div>
                    <button className="btn btn-sm shrink-0" onClick={() => track(s.name, s.pattern)}>
                      Track
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>

        <div className="min-w-0">
          {selected ? (
            <PersonLedger key={`${selected.id}-${fy}`} personId={selected.id} onChanged={() => (reload(), reloadSug(), bump())} />
          ) : (
            people && <Empty title="Pick or track a person">Their transactions will appear here as one running ledger.</Empty>
          )}
        </div>
      </div>
    </>
  );
}

function AddPerson({ onAdd }: { onAdd: (name: string, pattern: string) => void }) {
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState("");
  return (
    <form
      className="card mb-4 flex flex-wrap items-end gap-3 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        onAdd(name.trim(), pattern.trim() || name.trim().split(/\s+/)[0]);
      }}
    >
      <label className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="label">Name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Hrishikesh Reddy" autoFocus />
      </label>
      <label className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="label">Match bank narrations containing</span>
        <input className="input" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="first name, e.g. hrishi" />
      </label>
      <button className="btn btn-primary" disabled={!name.trim()}>
        Track
      </button>
      <p className="text-ink-3 w-full text-[12px]">
        Use the shortest part of the name the bank always prints. Banks cut names short (“Mr Hrishik”, “Hrishikesh Redd”), so a first name usually works
        best.
      </p>
    </form>
  );
}

function PersonLedger({ personId, onChanged }: { personId: number; onChanged: () => void }) {
  const { fy, toast, accountId } = useApp();
  const { data: d, reload } = useData(
    () => api.get<Ledger>(`/api/people/${personId}/ledger`, { fy, account_id: accountId }),
    [personId, fy, accountId],
  );
  const { data: cats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const [view, setView] = useState<"all" | "in" | "out">("all");
  const [month, setMonth] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const months = useMemo(
    () =>
      monthStats(
        d?.rows ?? [],
        (r) => r.date,
        (r) => r.received,
        (r) => r.sent,
      ),
    [d],
  );
  const rows = useMemo(
    () =>
      (d?.rows ?? [])
        .filter((r) => view === "all" || (view === "in" ? r.received : r.sent))
        .filter((r) => !month || r.date.startsWith(month))
        .slice()
        .reverse(),
    [d, view, month],
  );

  if (!d) return null;

  const netText =
    d.net === 0
      ? "Money in and out is exactly even."
      : d.net > 0
        ? `You received ${paise(d.net, true)} more than you sent.`
        : `You sent ${paise(-d.net, true)} more than you received.`;

  const remove = async () => {
    await api.send("DELETE", `/api/people/${personId}`);
    toast(`Stopped tracking ${d.person.name}. Their transactions are unchanged.`);
    window.location.hash = "";
    onChanged();
  };

  return (
    <div className="space-y-3">
      <section className="card p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[20px] font-semibold tracking-tight">{d.person.name}</h2>
            <p className="text-ink-3 mt-0.5 text-[12.5px]">
              Matches narrations containing <code className="bg-surface-2 rounded px-1">{d.person.pattern}</code>
              {d.names_seen.length > 0 && <> · seen as {d.names_seen.join(", ")}</>}
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-sm" onClick={() => setEditing((e) => !e)}>
              {editing ? "Close" : "Edit"}
            </button>
            {confirmDelete ? (
              <>
                <button className="btn btn-sm text-danger" onClick={remove}>
                  Stop tracking
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
                  Keep
                </button>
              </>
            ) : (
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(true)}>
                Remove
              </button>
            )}
          </div>
        </div>
        {editing && (
          <EditPerson
            person={d.person}
            onSaved={() => {
              setEditing(false);
              reload();
              onChanged();
            }}
          />
        )}

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Figure label="You received" value={paise(d.received, true)} hint={`${d.count_in} payments`} tone="credit" />
          <Figure label="You sent" value={paise(d.sent, true)} hint={`${d.count_out} payments`} />
          <Figure
            label="Net"
            value={`${d.net >= 0 ? "+" : "−"}${paise(Math.abs(d.net), true)}`}
            hint={d.net >= 0 ? "in your favour" : "you are out of pocket"}
            tone={d.net >= 0 ? "credit" : undefined}
          />
          <Figure label="Period" value={`${d.count} txns`} hint={d.first ? `${fmtDate(d.first)} – ${fmtDate(d.last)}` : "—"} />
        </div>
        <p className="text-ink-2 mt-3 text-[13.5px]">
          {netText} Largest single payment in: <span className="num">{paise(d.largest_in, true)}</span>, out:{" "}
          <span className="num">{paise(d.largest_out, true)}</span>.
        </p>
      </section>

      {d.monthly.length > 0 && (
        <section className="card p-4">
          <h3 className="text-[14px] font-semibold">Month by month</h3>
          <div className="mt-3 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.monthly} margin={{ left: 0, right: 4, top: 4, bottom: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="month" tickFormatter={monthLabel} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={compactInr} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={52} />
                <Tooltip
                  cursor={{ fill: "var(--surface-2)" }}
                  contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12, color: "var(--ink)" }}
                  labelFormatter={(m) => monthLabel(String(m))}
                  formatter={(v, name) => [paise(Number(v), true), name === "received" ? "Received" : "Sent"]}
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  height={24}
                  iconType="circle"
                  iconSize={8}
                  formatter={(v) => <span className="text-ink-2 text-[12px]">{v === "received" ? "Received" : "Sent"}</span>}
                />
                <Bar dataKey="received" fill="var(--credit)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="sent" fill="var(--ink-3)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <BulkCategorise ledger={d} cats={cats ?? []} onDone={() => (reload(), onChanged())} />

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 pb-2">
          <h3 className="text-[14px] font-semibold">{month ? monthTitle(month) : "All transactions"}</h3>
          <Segmented
            value={view}
            onChange={setView}
            options={[
              ["all", `All ${d.count}`],
              ["in", `Received ${d.count_in}`],
              ["out", `Sent ${d.count_out}`],
            ]}
          />
        </div>
        {months.length > 1 && (
          <div className="px-4 pb-3">
            <MonthStrip months={months} value={month} onChange={setMonth} />
          </div>
        )}
        <div className="max-h-[560px] overflow-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th className="text-right">Amount</th>
                <th className="text-right" title="Received minus sent, up to this row">
                  Running net
                </th>
                <th>Category</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="num text-ink-2">{fmtDate(r.date)}</td>
                  <td className="max-w-80">
                    <div className="text-ink-2 truncate font-mono text-[12px]" title={r.narration}>
                      {r.narration}
                    </div>
                    {r.note && <div className="text-[12px]">“{r.note}”</div>}
                  </td>
                  <td className={`num text-right font-medium ${r.received ? "text-credit" : ""}`}>
                    {r.received ? "+" : "−"}
                    {paise(r.received || r.sent, true)}
                  </td>
                  <td className="num text-ink-2 text-right">
                    {r.running_net >= 0 ? "+" : "−"}
                    {paise(Math.abs(r.running_net), true)}
                  </td>
                  <td>
                    {r.category ? (
                      <>
                        <div className="text-[12.5px]">{r.category}</div>
                        <StatusChip status={r.status} />
                      </>
                    ) : (
                      <span className="text-ink-3 text-[12.5px]">Not categorised</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function BulkCategorise({ ledger, cats, onDone }: { ledger: Ledger; cats: Category[]; onDone: () => void }) {
  const { toast } = useApp();
  const [inCat, setInCat] = useState<number | null>(null);
  const [outCat, setOutCat] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const inIds = ledger.rows.filter((r) => r.received).map((r) => r.id);
  const outIds = ledger.rows.filter((r) => r.sent).map((r) => r.id);

  const apply = async (ids: number[], category_id: number, what: string) => {
    setBusy(true);
    try {
      const r = await api.send<{ updated: number }>("POST", "/api/transactions/bulk-classify", { ids, category_id, confirm: true });
      toast(`Confirmed ${r.updated} ${what} payments.`);
      onDone();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card p-4">
      <h3 className="text-[14px] font-semibold">Say what this money was</h3>
      <p className="text-ink-3 mt-0.5 text-[12px]">
        {ledger.unconfirmed} of {ledger.count} are not confirmed. Pick a category for all money in and all money out. It confirms every row in that
        direction, and you can still change single rows in Transactions.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-credit w-24 text-[13px] font-medium">Received ({inIds.length})</span>
          <CategorySelect categories={cats} direction="credit" value={inCat} onChange={setInCat} className="min-w-0 flex-1" />
          <button className="btn btn-sm" disabled={!inCat || !inIds.length || busy} onClick={() => inCat && apply(inIds, inCat, "received")}>
            Apply
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-24 text-[13px] font-medium">Sent ({outIds.length})</span>
          <CategorySelect categories={cats} direction="debit" value={outCat} onChange={setOutCat} className="min-w-0 flex-1" />
          <button className="btn btn-sm" disabled={!outCat || !outIds.length || busy} onClick={() => outCat && apply(outIds, outCat, "sent")}>
            Apply
          </button>
        </div>
      </div>
      {ledger.by_category.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ledger.by_category.map((c) => (
            <span key={c.category} className="chip" title={`${c.count} transactions`}>
              {c.category} · {c.count}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function EditPerson({ person, onSaved }: { person: Ledger["person"]; onSaved: () => void }) {
  const { toast } = useApp();
  const [name, setName] = useState(person.name);
  const [pattern, setPattern] = useState(person.pattern);
  const [note, setNote] = useState(person.note);
  const [pinned, setPinned] = useState(person.pinned);
  return (
    <form
      className="border-line mt-3 grid gap-3 border-t pt-3 md:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.send("PUT", `/api/people/${person.id}`, { name, pattern, note, pinned });
          toast("Saved.");
          onSaved();
        } catch (err) {
          toast((err as Error).message, "error");
        }
      }}
    >
      <label className="flex flex-col gap-1">
        <span className="label">Name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="label">Match narrations containing</span>
        <input className="input" value={pattern} onChange={(e) => setPattern(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="label">Note (who this is, what the money is for)</span>
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
        Show in sidebar
      </label>
      <div className="md:text-right">
        <button className="btn btn-primary btn-sm">Save</button>
      </div>
    </form>
  );
}

function Figure({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "credit" }) {
  return (
    <div className="bg-surface-2 rounded-lg p-3">
      <div className="text-ink-3 text-[12px] font-medium">{label}</div>
      <div className={`num mt-0.5 text-[18px] font-semibold tracking-tight ${tone === "credit" ? "text-credit" : ""}`}>{value}</div>
      {hint && <div className="text-ink-3 mt-0.5 truncate text-[11.5px]">{hint}</div>}
    </div>
  );
}
