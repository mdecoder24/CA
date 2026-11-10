"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Empty, PageHeader, Stat, useApp } from "@/components/shell";
import { api, type Dashboard, fmtDate, monthLabel, paise } from "@/lib/api";
import { useData } from "@/lib/use-data";

const compact = (p: number) => {
  const r = p / 100;
  if (r >= 1e7) return `₹${(r / 1e7).toFixed(1)}Cr`;
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(1)}L`;
  if (r >= 1e3) return `₹${(r / 1e3).toFixed(0)}k`;
  return `₹${r.toFixed(0)}`;
};

export default function DashboardPage() {
  const { fy } = useApp();
  const { data: d, error } = useData(() => api.get<Dashboard>("/api/dashboard", { fy }), [fy]);

  if (error) return <Empty title="Could not load dashboard">{error}</Empty>;
  if (!d) return null;

  if (d.txn_count === 0)
    return (
      <>
        <PageHeader title="Dashboard" sub={`FY ${fy}`} />
        <Empty title="No transactions for this year yet">
          <Link href="/imports" className="btn btn-primary mt-4">
            Import a Kotak statement
          </Link>
        </Empty>
      </>
    );

  const totalHeads = d.income_heads.reduce((a, h) => a + h.amount, 0) || 1;

  return (
    <>
      <PageHeader
        title="Dashboard"
        sub={`FY ${fy} · ${d.txn_count} transactions`}
        actions={
          <Link href="/review" className="btn btn-primary">
            Review {d.unclassified_credits + d.open_flags > 0 ? `(${d.unclassified_credits})` : ""}
          </Link>
        }
      />

      {d.gaps.length > 0 && (
        <div className="bg-warn-soft text-warn mb-4 rounded-lg px-4 py-3 text-[13.5px]">
          <b>Statement gaps:</b> no statement covers{" "}
          {d.gaps.map((g, i) => (
            <span key={i}>
              {i > 0 && ", "}
              {fmtDate(g.from)} to {fmtDate(g.to)}
            </span>
          ))}
          . Credits in those periods are missing.{" "}
          <Link href="/imports" className="underline">
            Import them
          </Link>
          .
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Closing balance" value={paise(d.closing_balance, true)} />
        <Stat label="Total credits" value={paise(d.total_credits, true)} tone="credit" hint="Not the same as income" />
        <Stat label="Total debits" value={paise(d.total_debits, true)} />
        <Stat
          label="Credits to explain"
          value={d.unclassified_credits}
          tone={d.unclassified_credits ? "warn" : undefined}
          hint={
            d.unclassified_credits ? `${paise(d.unclassified_credit_amount, true)} · ${d.open_flags} flags open` : `${d.open_flags} flags open`
          }
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[1.6fr_1fr]">
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Money in and out by month</h2>
          <div className="mt-3 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.monthly} margin={{ left: 0, right: 4, top: 4, bottom: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="month" tickFormatter={monthLabel} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={compact} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={52} />
                <Tooltip
                  cursor={{ fill: "var(--surface-2)" }}
                  contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(m) => monthLabel(String(m))}
                  formatter={(v, name) => [paise(Number(v), true), name === "credits" ? "Credits" : "Debits"]}
                />
                <Bar dataKey="credits" fill="var(--credit)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="debits" fill="var(--ink-3)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Credits by income head</h2>
          <p className="text-ink-3 text-[12px]">Confirmed classifications only</p>
          <ul className="mt-3 space-y-2.5">
            {d.income_heads.map((h) => (
              <li key={h.head}>
                <div className="flex justify-between text-[13px]">
                  <span className={h.head === "Unconfirmed" || h.head === "Needs explanation" ? "text-warn" : ""}>{h.head}</span>
                  <span className="num">{paise(h.amount, true)}</span>
                </div>
                <div className="bg-surface-2 mt-1 h-1.5 overflow-hidden rounded-full">
                  <div
                    className={`h-full rounded-full ${h.head === "Unconfirmed" || h.head === "Needs explanation" ? "bg-warn" : "bg-accent"}`}
                    style={{ width: `${(h.amount / totalHeads) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {d.credit_categories.length > 0 && (
        <section className="card mt-3 overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Credit category (confirmed)</th>
                <th className="text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {d.credit_categories.map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td className="num text-right">{paise(c.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
