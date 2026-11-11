"use client";

import { CategoryBars, MonthlySpend, PlainSummary, RiskHeader, Signals, type Spend, TrackedPeople, TwoWay } from "@/components/spend-report";
import { Empty, PageHeader, useApp } from "@/components/shell";
import { api, fmtDate, paise } from "@/lib/api";
import { useData } from "@/lib/use-data";

export default function SpendPage() {
  const { fy, accountId } = useApp();
  const { data: d, error } = useData(() => api.get<Spend>("/api/spend", { fy, account_id: accountId }), [fy, accountId]);

  if (error) return <Empty title="Could not load spend analysis">{error}</Empty>;
  if (!d) return null;
  if (d.empty)
    return (
      <>
        <PageHeader title="Spend" sub={`FY ${fy}`} />
        <Empty title="No transactions for this year yet" />
      </>
    );

  const movedTotal = d.moved.reduce((a, m) => a + m.amount, 0);

  return (
    <>
      <PageHeader title="Spend" sub={`Where your money went in FY ${fy}, and how risky the pattern is. ${d.disclaimer}`} />

      <PlainSummary d={d} />

      <div className="mt-3">
        <RiskHeader d={d} />
      </div>

      {d.notes.filter((n) => !n.includes("not yet categorised")).length > 0 && (
        <div className="bg-warn-soft text-warn mt-3 rounded-lg px-4 py-3 text-[13px]">
          {d.notes.filter((n) => !n.includes("not yet categorised")).map((n, i) => (
            <div key={i}>{n}</div>
          ))}
        </div>
      )}

      <div className="mt-3 grid gap-3 lg:grid-cols-[1.15fr_1fr]">
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Risk signals</h2>
          <p className="text-ink-3 text-[12px]">Each signal adds to the score. Danger counts fully, watch counts half.</p>
          <div className="mt-1">
            <Signals d={d} />
          </div>
        </section>
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Spending by category</h2>
          <p className="text-ink-3 mb-3 text-[12px]">Includes suggested categories you haven’t confirmed yet</p>
          <CategoryBars d={d} />
        </section>
      </div>

      {d.people.length > 0 && (
        <div className="mt-3">
          <TrackedPeople d={d} />
        </div>
      )}

      <TwoWay d={d} />

      <section className="card mt-3 p-4">
        <h2 className="text-[14px] font-semibold">Spending by month</h2>
        <div className="mt-3">
          <MonthlySpend d={d} />
        </div>
      </section>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <section className="card overflow-x-auto">
          <div className="px-4 pt-4">
            <h2 className="text-[14px] font-semibold">Who you paid most</h2>
          </div>
          <table className="table mt-2">
            <thead>
              <tr>
                <th>Payee</th>
                <th className="text-right">Times</th>
                <th className="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {d.payees.map((p) => (
                <tr key={p.payee}>
                  <td>
                    <div className="font-medium">{p.payee}</div>
                    <div className="text-ink-3 text-[11.5px]">{p.category}</div>
                  </td>
                  <td className="num text-right">{p.count}</td>
                  <td className="num text-right">{paise(p.amount, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card overflow-x-auto">
          <div className="px-4 pt-4">
            <h2 className="text-[14px] font-semibold">Biggest single spends</h2>
          </div>
          <table className="table mt-2">
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th className="text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {d.biggest.map((b) => (
                <tr key={b.id}>
                  <td className="num text-ink-2">{fmtDate(b.date)}</td>
                  <td>
                    <div className="font-mono text-[12px] break-words">{b.narration}</div>
                    <div className="text-ink-3 text-[11.5px]">{b.category}</div>
                  </td>
                  <td className="num text-right">{paise(b.amount, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Small payments add up</h2>
          <p className="text-ink-2 mt-1 text-[13px]">
            <span className="num font-semibold">{d.small_tickets.count}</span> UPI payments under {paise(d.small_tickets.under, true)} (about{" "}
            {d.small_tickets.per_month} a month), totalling <span className="num font-semibold">{paise(d.small_tickets.amount, true)}</span>.
          </p>
        </section>
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Moved, not spent</h2>
          <p className="text-ink-3 text-[12px]">Own-account transfers, investments, trading deposits and tax. Not counted as spending.</p>
          <ul className="mt-2 space-y-1 text-[13px]">
            {d.moved.map((m) => (
              <li key={m.label} className="flex justify-between">
                <span>{m.label}</span>
                <span className="num">{paise(m.amount, true)}</span>
              </li>
            ))}
            {d.moved.length > 0 && (
              <li className="border-line flex justify-between border-t pt-1 font-semibold">
                <span>Total</span>
                <span className="num">{paise(movedTotal, true)}</span>
              </li>
            )}
          </ul>
        </section>
      </div>
    </>
  );
}
