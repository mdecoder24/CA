"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtDate, monthLabel, paise } from "@/lib/api";

export type Signal = { key: string; level: "ok" | "watch" | "danger"; title: string; detail: string; weight: number };
export type Spend = {
  start: string;
  end: string;
  empty: boolean;
  first_txn: string;
  last_txn: string;
  months: number;
  spend_total: number;
  monthly_avg: number;
  inflow: number;
  uncategorised: number;
  spend_on_suggestion: number;
  closing_balance: number | null;
  min_balance: number | null;
  categories: { category: string; amount: number; count: number; share: number }[];
  payees: { payee: string; amount: number; count: number; category: string }[];
  monthly: { month: string; spend: number; inflow: number }[];
  moved: { label: string; amount: number }[];
  biggest: { id: number; date: string; amount: number; category: string; payee: string; narration: string }[];
  small_tickets: { count: number; amount: number; per_month: number; under: number };
  risk: { score: number; level: "low" | "moderate" | "high" | "critical"; signals: Signal[] };
  notes: string[];
  disclaimer: string;
  two_way: { name: string; aliases: string[]; received: number; sent: number; net: number; count_in: number; count_out: number }[];
  pass_through: number;
};

const LEVEL = {
  low: { label: "Low risk", cls: "chip-ok", icon: "✓", ink: "text-accent" },
  moderate: { label: "Moderate risk", cls: "chip-warn", icon: "!", ink: "text-warn" },
  high: { label: "High risk", cls: "chip-danger", icon: "!", ink: "text-danger" },
  critical: { label: "Critical risk", cls: "chip-danger", icon: "✕", ink: "text-danger" },
} as const;

const SIG = {
  ok: { label: "OK", cls: "chip-ok", icon: "✓" },
  watch: { label: "Watch", cls: "chip-warn", icon: "!" },
  danger: { label: "Danger", cls: "chip-danger", icon: "✕" },
} as const;

const compact = (p: number) => {
  const r = p / 100;
  if (r >= 1e7) return `₹${(r / 1e7).toFixed(1)}Cr`;
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(1)}L`;
  if (r >= 1e3) return `₹${(r / 1e3).toFixed(0)}k`;
  return `₹${r.toFixed(0)}`;
};

export function RiskHeader({ d }: { d: Spend }) {
  const lv = LEVEL[d.risk.level];
  return (
    <div className="grid gap-3 sm:grid-cols-[auto_1fr] sm:items-center">
      <div className="card flex items-center gap-4 p-4 sm:min-w-56">
        <div>
          <div className="text-ink-3 text-[12px] font-medium">Spending risk</div>
          <div className={`num text-[34px] leading-none font-semibold tracking-tight ${lv.ink}`}>
            {d.risk.score}
            <span className="text-ink-3 text-[15px] font-medium">/100</span>
          </div>
          <span className={`chip mt-2 ${lv.cls}`}>
            <span aria-hidden>{lv.icon}</span>
            {lv.label}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Spent" value={paise(d.spend_total, true)} hint={`${fmtDate(d.first_txn)} – ${fmtDate(d.last_txn)}`} />
        <Tile label="Per month" value={paise(d.monthly_avg, true)} hint={`over ${d.months.toFixed(1)} months`} />
        <Tile label="New money in" value={paise(d.inflow, true)} hint="excl. own transfers, refunds" />
        <Tile label="Lowest balance" value={paise(d.min_balance, true)} hint={`closing ${paise(d.closing_balance, true)}`} />
      </div>
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card p-3.5">
      <div className="text-ink-3 text-[12px] font-medium">{label}</div>
      <div className="num mt-0.5 text-[18px] font-semibold tracking-tight">{value}</div>
      {hint && <div className="text-ink-3 mt-0.5 truncate text-[11.5px]">{hint}</div>}
    </div>
  );
}

export function Signals({ d, onlyProblems = false }: { d: Spend; onlyProblems?: boolean }) {
  const order = { danger: 0, watch: 1, ok: 2 };
  const list = [...d.risk.signals].sort((a, b) => order[a.level] - order[b.level]).filter((s) => !onlyProblems || s.level !== "ok");
  if (!list.length) return <p className="text-ink-2 text-[13px]">No warning signs in this period.</p>;
  return (
    <ul className="divide-line divide-y">
      {list.map((s) => {
        const l = SIG[s.level];
        return (
          <li key={s.key} className="flex gap-3 py-2.5">
            <span className={`chip ${l.cls} mt-0.5 w-[72px] justify-center`}>
              <span aria-hidden>{l.icon}</span>
              {l.label}
            </span>
            <div className="min-w-0">
              <div className="text-[13.5px] font-semibold">{s.title}</div>
              <div className="text-ink-2 text-[13px]">{s.detail}</div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function CategoryBars({ d, limit = 12 }: { d: Spend; limit?: number }) {
  const max = d.categories[0]?.amount || 1;
  return (
    <ul className="space-y-2.5">
      {d.categories.slice(0, limit).map((c) => {
        const unc = c.category === "Not yet categorised";
        return (
          <li key={c.category} title={`${c.count} transactions`}>
            <div className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className={`truncate ${unc ? "text-ink-2 italic" : ""}`}>{c.category}</span>
              <span className="num shrink-0">
                {paise(c.amount, true)} <span className="text-ink-3 text-[11.5px]">{(c.share * 100).toFixed(0)}%</span>
              </span>
            </div>
            <div className="bg-surface-2 mt-1 h-2 overflow-hidden rounded-full">
              <div className={`h-full rounded-full ${unc ? "bg-ink-3" : "bg-accent"}`} style={{ width: `${(c.amount / max) * 100}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function MonthlySpend({ d }: { d: Spend }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={d.monthly} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="month" tickFormatter={monthLabel} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={compact} tick={{ fill: "var(--ink-3)", fontSize: 11 }} axisLine={false} tickLine={false} width={52} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12, color: "var(--ink)" }}
            labelFormatter={(m) => monthLabel(String(m))}
            formatter={(v) => [paise(Number(v), true), "Spent"]}
          />
          <Bar dataKey="spend" fill="var(--accent)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Compact snapshot shown right after a statement is imported. */
export function SpendSnapshot({ d, onClose }: { d: Spend; onClose?: () => void }) {
  if (d.empty) return null;
  return (
    <section className="card mt-4 p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[15px] font-semibold">Where the money went in this statement</h2>
          <p className="text-ink-3 text-[12px]">{d.disclaimer}</p>
        </div>
        <div className="flex gap-2">
          <Link href="/spend" className="btn btn-sm">
            Full spend analysis
          </Link>
          {onClose && (
            <button className="btn btn-ghost btn-sm" onClick={onClose}>
              Close
            </button>
          )}
        </div>
      </div>
      <div className="mt-3">
        <RiskHeader d={d} />
      </div>
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="text-ink-2 mb-2 text-[12.5px] font-semibold">Top spending</h3>
          <CategoryBars d={d} limit={6} />
        </div>
        <div>
          <h3 className="text-ink-2 mb-1 text-[12.5px] font-semibold">What needs attention</h3>
          <Signals d={d} onlyProblems />
        </div>
      </div>
      {d.notes.length > 0 && (
        <ul className="text-ink-2 mt-3 space-y-1 text-[12.5px]">
          {d.notes.map((n, i) => (
            <li key={i}>• {n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** People who both sent you money and received money from you (not yet categorised). */
export function TwoWay({ d }: { d: Spend }) {
  if (!d.two_way.length) return null;
  return (
    <section className="card mt-3 overflow-x-auto">
      <div className="px-4 pt-4">
        <h2 className="text-[14px] font-semibold">Two-way money</h2>
        <p className="text-ink-3 text-[12px]">
          People who both paid you and were paid by you. Money going back and forth (loans, splits, your own money held by someone) is not real spending.
          Names are grouped by how they start, because the bank cuts them short.
        </p>
      </div>
      <table className="table mt-2">
        <thead>
          <tr>
            <th>Person</th>
            <th className="text-right">You received</th>
            <th className="text-right">You sent</th>
            <th className="text-right">Net</th>
          </tr>
        </thead>
        <tbody>
          {d.two_way.map((f) => (
            <tr key={f.name}>
              <td>
                <div className="font-medium">{f.name}</div>
                {f.aliases.length > 1 && <div className="text-ink-3 text-[11.5px]">also: {f.aliases.filter((a) => a !== f.name).join(", ")}</div>}
              </td>
              <td className="num text-credit text-right">
                {paise(f.received, true)}
                <div className="text-ink-3 text-[11px]">{f.count_in}×</div>
              </td>
              <td className="num text-right">
                {paise(f.sent, true)}
                <div className="text-ink-3 text-[11px]">{f.count_out}×</div>
              </td>
              <td className={`num text-right font-semibold ${f.net >= 0 ? "text-credit" : ""}`}>
                {f.net >= 0 ? "+" : "−"}
                {paise(Math.abs(f.net), true)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
