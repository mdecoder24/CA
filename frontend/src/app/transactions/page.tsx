"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { CategorySelect } from "@/components/category-select";
import { type MonthStat, monthStats, MonthStrip, monthTitle } from "@/components/month-strip";
import { Segmented } from "@/components/segmented";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Category, fmtDate, paise, type PersonSummary, type Txn } from "@/lib/api";
import { useData } from "@/lib/use-data";

const MONTHS_PER_PAGE = 3;

const STATUS_DOT: Record<string, { cls: string; label: string }> = {
  confirmed: { cls: "bg-accent", label: "Confirmed" },
  suggested: { cls: "bg-warn", label: "Suggested" },
  unclassified: { cls: "bg-ink-3", label: "Not categorised" },
};

export default function TransactionsPage() {
  const { fy, toast, bump } = useApp();
  const [direction, setDirection] = useState<"" | "credit" | "debit">("");
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [personId, setPersonId] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [q, setQ] = useState("");
  // "latest" = the most recent month that has entries; "" = all months.
  const [month, setMonth] = useState("latest");
  const [monthsShown, setMonthsShown] = useState(MONTHS_PER_PAGE);
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

  const months = useMemo(
    () =>
      monthStats(
        txs ?? [],
        (t) => t.txn_date,
        (t) => t.credit,
        (t) => t.debit,
      ),
    [txs],
  );

  // Selected month, falling back gracefully when filters leave it empty.
  const active =
    month === "latest" ? (months.at(-1)?.month ?? "") : month && !months.some((m) => m.month === month) ? (months.at(-1)?.month ?? "") : month;

  // Rows per month, newest month first and newest row first inside each month.
  const byMonth = useMemo(() => {
    const map = new Map<string, Txn[]>();
    for (const t of txs ?? []) {
      const m = t.txn_date.slice(0, 7);
      if (!map.has(m)) map.set(m, []);
      map.get(m)!.push(t);
    }
    for (const list of map.values()) list.reverse();
    return map;
  }, [txs]);

  const visibleMonths: MonthStat[] = active
    ? months.filter((m) => m.month === active)
    : months.slice().reverse().slice(0, monthsShown);

  const sel = active ? months.find((m) => m.month === active) : null;
  const totals = sel
    ? { credit: sel.credit, debit: sel.debit, count: sel.count }
    : months.reduce((a, m) => ({ credit: a.credit + m.credit, debit: a.debit + m.debit, count: a.count + m.count }), { credit: 0, debit: 0, count: 0 });

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
  };

  return (
    <>
      <PageHeader title="Transactions" sub={`FY ${fy}, one month at a time. Bank details are shown exactly as printed; only the category can be changed.`} />

      {/* Filters */}
      <section className="card mb-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            value={direction}
            onChange={setDirection}
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
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search"
          />
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">Any status</option>
            <option value="unconfirmed">Needs review</option>
            <option value="confirmed">Confirmed</option>
          </select>
          <select className="select max-w-52" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} aria-label="Category">
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
            <select className="select max-w-48" value={personId} onChange={(e) => setPersonId(e.target.value)} aria-label="Person">
              <option value="">Anyone</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <label className="text-ink-2 flex items-center gap-1.5 text-[13px]">
            <input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} />
            Flagged only
          </label>
          {filtersOn && (
            <button className="btn btn-ghost btn-sm" onClick={clear}>
              Clear filters
            </button>
          )}
        </div>
      </section>

      {/* Month picker */}
      {months.length > 0 && (
        <div className="mb-3">
          <MonthStrip
            months={months}
            value={active}
            onChange={(m) => {
              setMonth(m);
              setMonthsShown(MONTHS_PER_PAGE);
            }}
          />
        </div>
      )}

      {/* Totals for the selected month (or all months) */}
      <div className="mb-3 grid grid-cols-3 gap-3">
        <Total label="Money in" value={paise(totals.credit, true)} hint={sel ? monthTitle(sel.month) : "all months"} tone="credit" />
        <Total label="Money out" value={paise(totals.debit, true)} hint={sel ? monthTitle(sel.month) : "all months"} />
        <Total
          label="Net"
          value={`${totals.credit - totals.debit >= 0 ? "+" : "−"}${paise(Math.abs(totals.credit - totals.debit), true)}`}
          hint={`${totals.count} entries${filtersOn ? ", filtered" : ""}`}
        />
      </div>

      {txs?.length === 0 && (
        <div className="card text-ink-3 p-10 text-center text-[13.5px]">Nothing matches these filters.</div>
      )}

      <div className="space-y-4">
        {visibleMonths.map((m) => (
          <MonthCard key={m.month} stat={m} rows={byMonth.get(m.month) ?? []} cats={cats ?? []} onCategory={setCat} />
        ))}
      </div>

      {!active && months.length > monthsShown && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <span className="text-ink-3 text-[12.5px]">
            Showing {monthsShown} of {months.length} months
          </span>
          <button className="btn btn-sm" onClick={() => setMonthsShown((n) => n + MONTHS_PER_PAGE)}>
            Show older months
          </button>
        </div>
      )}
    </>
  );
}

function MonthCard({
  stat,
  rows,
  cats,
  onCategory,
}: {
  stat: MonthStat;
  rows: Txn[];
  cats: Category[];
  onCategory: (t: Txn, id: number) => void;
}) {
  const net = stat.credit - stat.debit;
  const review = rows.filter((r) => r.status !== "confirmed").length;
  return (
    <section className="card overflow-hidden">
      <header className="border-line flex flex-wrap items-end justify-between gap-3 border-b px-4 py-3">
        <div>
          <h2 className="text-[16px] font-semibold tracking-tight">{monthTitle(stat.month)}</h2>
          <p className="text-ink-3 text-[12px]">
            {stat.count} entries{review > 0 && <> · {review} need review</>}
          </p>
        </div>
        <div className="num flex gap-5 text-right text-[12px]">
          <div>
            <div className="text-ink-3">In</div>
            <div className="text-credit text-[14px] font-semibold">{paise(stat.credit, true)}</div>
          </div>
          <div>
            <div className="text-ink-3">Out</div>
            <div className="text-[14px] font-semibold">{paise(stat.debit, true)}</div>
          </div>
          <div>
            <div className="text-ink-3">Net</div>
            <div className={`text-[14px] font-semibold ${net >= 0 ? "text-credit" : ""}`}>
              {net >= 0 ? "+" : "−"}
              {paise(Math.abs(net), true)}
            </div>
          </div>
        </div>
      </header>
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
            {rows.map((t) => {
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
                      categories={cats}
                      direction={t.direction}
                      value={t.category_id}
                      onChange={(id) => onCategory(t, id)}
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
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Total({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "credit" }) {
  return (
    <div className="card p-3.5">
      <div className="text-ink-3 text-[12px] font-medium">{label}</div>
      <div className={`num mt-0.5 text-[18px] font-semibold tracking-tight ${tone === "credit" ? "text-credit" : ""}`}>{value}</div>
      <div className="text-ink-3 truncate text-[11.5px]">{hint}</div>
    </div>
  );
}
