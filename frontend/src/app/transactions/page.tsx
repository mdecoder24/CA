"use client";

import Link from "next/link";
import { Fragment, useDeferredValue, useMemo, useState } from "react";
import { CategorySelect } from "@/components/category-select";
import { Segmented } from "@/components/segmented";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Category, fmtDate, paise, type PersonSummary, type Txn } from "@/lib/api";
import { useData } from "@/lib/use-data";

const PAGE = 250;

const STATUS_DOT: Record<string, { cls: string; label: string }> = {
  confirmed: { cls: "bg-accent", label: "Confirmed" },
  suggested: { cls: "bg-warn", label: "Suggested" },
  unclassified: { cls: "bg-ink-3", label: "Not categorised" },
};

function monthTitle(ym: string) {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "long", year: "numeric" });
}

export default function TransactionsPage() {
  const { fy, toast, bump } = useApp();
  const [direction, setDirection] = useState<"" | "credit" | "debit">("");
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [personId, setPersonId] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);
  const dq = useDeferredValue(q);

  const { data: cats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const { data: people } = useData(() => api.get<PersonSummary[]>("/api/people", { fy }), [fy]);
  const { data: txs, reload } = useData(
    () =>
      api.get<Txn[]>("/api/transactions", {
        fy,
        direction,
        status,
        category_id: categoryId,
        q: dq,
        flagged: flagged || undefined,
        person_id: personId,
      }),
    [fy, direction, status, categoryId, dq, flagged, personId],
  );

  // Newest first, grouped by month with totals.
  const groups = useMemo(() => {
    const list = (txs ?? []).slice().reverse().slice(0, shown);
    const out: { month: string; rows: Txn[]; credit: number; debit: number }[] = [];
    for (const t of list) {
      const m = t.txn_date.slice(0, 7);
      let g = out[out.length - 1];
      if (!g || g.month !== m) out.push((g = { month: m, rows: [], credit: 0, debit: 0 }));
      g.rows.push(t);
      g.credit += t.credit;
      g.debit += t.debit;
    }
    return out;
  }, [txs, shown]);

  const totals = useMemo(() => {
    const r = { credit: 0, debit: 0, nIn: 0, nOut: 0 };
    for (const t of txs ?? []) {
      r.credit += t.credit;
      r.debit += t.debit;
      if (t.credit) r.nIn++;
      else r.nOut++;
    }
    return r;
  }, [txs]);

  const setCat = async (t: Txn, id: number) => {
    try {
      await api.send("PATCH", `/api/transactions/${t.id}/classification`, { category_id: id, confirm: true });
      reload();
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const filtersOn = direction || status || categoryId || personId || flagged || q;
  const clear = () => {
    setDirection("");
    setStatus("");
    setCategoryId("");
    setPersonId("");
    setFlagged(false);
    setQ("");
    setShown(PAGE);
  };

  return (
    <>
      <PageHeader title="Transactions" sub={`Every bank entry in FY ${fy}, newest first. Bank details are shown exactly as printed; only the category can be changed.`} />

      {/* Filters */}
      <section className="card mb-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            value={direction}
            onChange={(v) => (setDirection(v), setShown(PAGE))}
            options={[
              ["", "All"],
              ["credit", "Money in"],
              ["debit", "Money out"],
            ]}
          />
          <input
            className="input min-w-0 flex-1 sm:max-w-72"
            placeholder="Search name, narration, ref, note…"
            value={q}
            onChange={(e) => (setQ(e.target.value), setShown(PAGE))}
            aria-label="Search"
          />
          <select className="select" value={status} onChange={(e) => (setStatus(e.target.value), setShown(PAGE))} aria-label="Status">
            <option value="">Any status</option>
            <option value="unconfirmed">Needs review</option>
            <option value="confirmed">Confirmed</option>
          </select>
          <select className="select max-w-52" value={categoryId} onChange={(e) => (setCategoryId(e.target.value), setShown(PAGE))} aria-label="Category">
            <option value="">Any category</option>
            <optgroup label="Money in">
              {cats
                ?.filter((c) => c.direction === "credit")
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </optgroup>
            <optgroup label="Money out">
              {cats
                ?.filter((c) => c.direction === "debit")
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </optgroup>
          </select>
          {people && people.length > 0 && (
            <select className="select max-w-48" value={personId} onChange={(e) => (setPersonId(e.target.value), setShown(PAGE))} aria-label="Person">
              <option value="">Anyone</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <label className="text-ink-2 flex items-center gap-1.5 text-[13px]">
            <input type="checkbox" checked={flagged} onChange={(e) => (setFlagged(e.target.checked), setShown(PAGE))} />
            Flagged only
          </label>
          {filtersOn && (
            <button className="btn btn-ghost btn-sm" onClick={clear}>
              Clear filters
            </button>
          )}
        </div>
      </section>

      {/* Totals for what is shown */}
      <div className="mb-3 grid grid-cols-3 gap-3">
        <Total label="Money in" value={paise(totals.credit, true)} hint={`${totals.nIn} entries`} tone="credit" />
        <Total label="Money out" value={paise(totals.debit, true)} hint={`${totals.nOut} entries`} />
        <Total
          label="Net"
          value={`${totals.credit - totals.debit >= 0 ? "+" : "−"}${paise(Math.abs(totals.credit - totals.debit), true)}`}
          hint={filtersOn ? "for these filters" : "for the year"}
        />
      </div>

      <section className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th className="w-24">Date</th>
                <th>Who / bank narration</th>
                <th className="w-56">Category</th>
                <th className="w-36 text-right">Amount</th>
                <th className="hidden w-32 text-right md:table-cell">Balance after</th>
              </tr>
            </thead>
            <tbody>
              {txs?.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-ink-3 py-10 text-center">
                    Nothing matches these filters.
                  </td>
                </tr>
              )}
              {groups.map((g) => (
                <Fragment key={g.month}>
                  <tr className="bg-surface-2">
                    <td colSpan={5} className="py-2">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="text-[13px] font-semibold">{monthTitle(g.month)}</span>
                        <span className="num text-ink-2 text-[12px]">
                          in <span className="text-credit">{paise(g.credit, true)}</span> · out {paise(g.debit, true)}
                        </span>
                      </div>
                    </td>
                  </tr>
                  {g.rows.map((t) => {
                    const dot = STATUS_DOT[t.status];
                    const openFlags = t.flags.filter((f) => !f.resolved);
                    return (
                      <tr key={t.id}>
                        <td className="num text-ink-2 text-[12.5px]">{fmtDate(t.txn_date)}</td>
                        <td className="min-w-64">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-[13.5px] font-medium">{t.counterparty || <span className="text-ink-3">Unknown payee</span>}</span>
                            {t.person && (
                              <Link href={`/people#${t.person_id}`} className="chip chip-ok">
                                {t.person}
                              </Link>
                            )}
                            {openFlags.map((f) => (
                              <span key={f.id} className="chip chip-warn" title={f.detail}>
                                {f.type.replaceAll("_", " ")}
                              </span>
                            ))}
                          </div>
                          <div className="text-ink-3 mt-0.5 truncate font-mono text-[11.5px]" title={t.raw_description}>
                            {t.raw_description}
                          </div>
                          {t.note && <div className="text-ink-2 mt-0.5 text-[12px]">“{t.note}”</div>}
                        </td>
                        <td>
                          <CategorySelect
                            categories={cats ?? []}
                            direction={t.direction}
                            value={t.category_id}
                            onChange={(id) => setCat(t, id)}
                            className="h-8 w-full text-[12.5px]"
                          />
                          <div className="text-ink-3 mt-1 flex items-center gap-1.5 text-[11.5px]">
                            <span className={`inline-block size-1.5 rounded-full ${dot.cls}`} aria-hidden />
                            {dot.label}
                            {t.source === "rule" && t.status !== "confirmed" && " by rule"}
                          </div>
                        </td>
                        <td className={`num text-right text-[14px] font-semibold ${t.credit ? "text-credit" : ""}`}>
                          {t.credit ? "+" : "−"}
                          {paise(t.credit || t.debit)}
                        </td>
                        <td className="num text-ink-3 hidden text-right text-[12.5px] md:table-cell">{paise(t.balance)}</td>
                      </tr>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {txs && txs.length > shown && (
          <div className="border-line flex items-center justify-center gap-3 border-t p-3">
            <span className="text-ink-3 text-[12.5px]">
              Showing {shown} of {txs.length}
            </span>
            <button className="btn btn-sm" onClick={() => setShown((s) => s + PAGE)}>
              Show {Math.min(PAGE, txs.length - shown)} more
            </button>
          </div>
        )}
      </section>
    </>
  );
}

function Total({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "credit" }) {
  return (
    <div className="card p-3.5">
      <div className="text-ink-3 text-[12px] font-medium">{label}</div>
      <div className={`num mt-0.5 text-[18px] font-semibold tracking-tight ${tone === "credit" ? "text-credit" : ""}`}>{value}</div>
      <div className="text-ink-3 text-[11.5px]">{hint}</div>
    </div>
  );
}
