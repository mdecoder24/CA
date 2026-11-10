"use client";

import { useEffect, useRef, useState } from "react";
import { Empty, PageHeader, useApp } from "@/components/shell";
import { api, rupees, type TaxEstimate } from "@/lib/api";
import { useData } from "@/lib/use-data";

type Inputs = {
  salary: { gross: number | null; exempt_allowances: number; hra_exempt: number; professional_tax: number; employer_nps_80ccd2: number };
  tds: { head: string; deductor: string; amount: number }[];
  taxes_paid: { kind: string; date: string; amount: number }[];
  deductions_old: Record<string, number>;
  trading: Record<string, number>;
  profession: { presumptive_44ada: boolean; extra_expenses: number };
};

const HEADS = [
  ["salary", "Salary"],
  ["profession", "Freelance / professional"],
  ["interest", "Interest (FD etc.)"],
  ["dividend", "Dividend"],
  ["other", "Other"],
];

function Num({ label, value, onChange, hint }: { label: string; value: number | null; onChange: (v: number | null) => void; hint?: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label">{label}</span>
      <input
        className="input num"
        inputMode="decimal"
        value={value ?? ""}
        placeholder="0"
        onChange={(e) => {
          const v = e.target.value.replace(/[,₹\s]/g, "");
          onChange(v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : value);
        }}
      />
      {hint && <span className="text-ink-3 text-[11.5px]">{hint}</span>}
    </label>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <h2 className="text-[14px] font-semibold">{title}</h2>
      {sub && <p className="text-ink-3 mt-0.5 text-[12px]">{sub}</p>}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export default function TaxPage() {
  const { fy } = useApp();
  const { data, error } = useData(() => api.get<{ inputs: Inputs; estimate: TaxEstimate }>(`/api/tax/${fy}`), [fy]);
  if (error) return <Empty title={`No tax rules for FY ${fy}`}>{error}</Empty>;
  if (!data || data.estimate.fy !== fy) return null;
  return <TaxForm key={fy} fy={fy} initial={data} />;
}

function TaxForm({ fy, initial }: { fy: string; initial: { inputs: Inputs; estimate: TaxEstimate } }) {
  const { toast } = useApp();
  const [inp, setInp] = useState<Inputs>(initial.inputs);
  const [est, setEst] = useState<TaxEstimate>(initial.estimate);
  const [dirty, setDirty] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Autosave 600ms after the last edit; the estimate updates with it.
  useEffect(() => {
    if (!dirty) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await api.send<{ estimate: TaxEstimate }>("PUT", `/api/tax/${fy}/inputs`, inp);
        setEst(r.estimate);
        setDirty(false);
      } catch (e) {
        toast((e as Error).message, "error");
      }
    }, 600);
  }, [inp, dirty, fy, toast]);

  const up = (fn: (d: Inputs) => void) => {
    const next = structuredClone(inp);
    fn(next);
    setInp(next);
    setDirty(true);
  };

  const n = est.regimes.new;
  const o = est.regimes.old;
  const labels = [...new Set([...o.lines, ...n.lines].map((l) => l.label))];
  const byN = Object.fromEntries(n.lines.map((l) => [l.label, l]));
  const byO = Object.fromEntries(o.lines.map((l) => [l.label, l]));

  return (
    <>
      <PageHeader title="Tax estimate" sub={`${est.label} · ${est.act}`} actions={<span className="text-ink-3 text-[12px]">{dirty ? "Saving…" : "Saved"}</span>} />

      <div className="bg-warn-soft text-warn mb-4 rounded-lg px-4 py-3 text-[13.5px] font-medium">{est.disclaimer}</div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <div className="space-y-3">
          <Section title="Salary (from Form 16 / payslips)" sub={`Bank shows ${rupees(est.salary_bank_net)} of confirmed salary credits (after deductions).`}>
            <Num label="Gross salary" value={inp.salary.gross} onChange={(v) => up((d) => void (d.salary.gross = v))} hint="Leave blank to estimate from bank credits" />
            <Num label="Professional tax" value={inp.salary.professional_tax} onChange={(v) => up((d) => void (d.salary.professional_tax = v ?? 0))} />
            <Num label="HRA exemption (old regime)" value={inp.salary.hra_exempt} onChange={(v) => up((d) => void (d.salary.hra_exempt = v ?? 0))} />
            <Num label="Other exempt allowances (old)" value={inp.salary.exempt_allowances} onChange={(v) => up((d) => void (d.salary.exempt_allowances = v ?? 0))} />
            <Num label="Employer NPS 80CCD(2)" value={inp.salary.employer_nps_80ccd2} onChange={(v) => up((d) => void (d.salary.employer_nps_80ccd2 = v ?? 0))} />
          </Section>

          <Section title="Freelance / professional income" sub="Receipts come from credits confirmed as “Freelance / Professional receipt”.">
            <label className="flex items-center gap-2 text-[13.5px] sm:col-span-2">
              <input
                type="checkbox"
                checked={inp.profession.presumptive_44ada}
                onChange={(e) => up((d) => void (d.profession.presumptive_44ada = e.target.checked))}
              />
              Use presumptive taxation (44ADA: 50% of receipts is profit)
            </label>
            {!inp.profession.presumptive_44ada && (
              <Num
                label="Expenses not paid from Kotak"
                value={inp.profession.extra_expenses}
                onChange={(v) => up((d) => void (d.profession.extra_expenses = v ?? 0))}
                hint="Debits tagged “Business expense” are added automatically"
              />
            )}
          </Section>

          <Section title="Trading & capital gains" sub="From your broker’s P&L / tax report. Use negative numbers for losses.">
            <Num label="F&O profit / loss" value={inp.trading.fno_pnl} onChange={(v) => up((d) => void (d.trading.fno_pnl = v ?? 0))} hint="Non-speculative business income" />
            <Num label="F&O turnover" value={inp.trading.fno_turnover} onChange={(v) => up((d) => void (d.trading.fno_turnover = v ?? 0))} hint="For your CA (audit check)" />
            <Num label="Intraday equity profit / loss" value={inp.trading.intraday_pnl} onChange={(v) => up((d) => void (d.trading.intraday_pnl = v ?? 0))} hint="Speculative business income" />
            <Num label="STCG on listed equity (111A)" value={inp.trading.stcg_111a} onChange={(v) => up((d) => void (d.trading.stcg_111a = v ?? 0))} />
            <Num label="LTCG on listed equity (112A)" value={inp.trading.ltcg_112a} onChange={(v) => up((d) => void (d.trading.ltcg_112a = v ?? 0))} />
            <Num label="Other gains taxed at slab" value={inp.trading.other_cg_slab} onChange={(v) => up((d) => void (d.trading.other_cg_slab = v ?? 0))} hint="e.g. debt funds bought after Apr 2023" />
          </Section>

          <Section title="Deductions (old regime only)">
            {[
              ["80C", "80C (PPF, ELSS, LIC, EPF…)"],
              ["80D", "80D (health insurance)"],
              ["80CCD1B", "80CCD(1B) (own NPS)"],
              ["80G", "80G (donations, eligible amount)"],
              ["home_loan_interest", "Home-loan interest (self-occupied)"],
              ["other", "Other deductions"],
            ].map(([k, l]) => (
              <Num key={k} label={l} value={inp.deductions_old[k] ?? 0} onChange={(v) => up((d) => void (d.deductions_old[k] = v ?? 0))} />
            ))}
          </Section>

          <EntryList
            title="TDS deducted"
            sub="From Form 16 / 16A / 26AS. Each entry names its income head so it is grossed up once."
            rows={inp.tds}
            onChange={(rows) => up((d) => void (d.tds = rows as Inputs["tds"]))}
            blank={{ head: "profession", deductor: "", amount: 0 }}
            render={(r, set) => (
              <>
                <select className="select" value={r.head} onChange={(e) => set({ ...r, head: e.target.value })} aria-label="Income head">
                  {HEADS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
                <input className="input min-w-0 flex-1" placeholder="Deductor" value={r.deductor} onChange={(e) => set({ ...r, deductor: e.target.value })} />
              </>
            )}
          />
          <EntryList
            title="Advance / self-assessment tax paid"
            rows={inp.taxes_paid}
            onChange={(rows) => up((d) => void (d.taxes_paid = rows as Inputs["taxes_paid"]))}
            blank={{ kind: "advance", date: "", amount: 0 }}
            render={(r, set) => (
              <>
                <select className="select" value={r.kind} onChange={(e) => set({ ...r, kind: e.target.value })} aria-label="Kind">
                  <option value="advance">Advance tax</option>
                  <option value="self_assessment">Self-assessment</option>
                </select>
                <input type="date" className="input" value={r.date} onChange={(e) => set({ ...r, date: e.target.value })} />
              </>
            )}
          />
        </div>

        <div className="xl:sticky xl:top-6 xl:self-start">
          <div className="grid grid-cols-2 gap-3">
            {(["new", "old"] as const).map((k) => {
              const r = est.regimes[k];
              const best = est.recommended === k;
              return (
                <div key={k} className={`card p-4 ${best ? "ring-accent ring-2" : ""}`}>
                  <div className="text-ink-3 text-[12px] font-medium">{r.name}</div>
                  <div className="num mt-1 text-[20px] font-semibold">{rupees(r.liability)}</div>
                  <div className={`num text-[12.5px] ${r.balance > 0 ? "text-warn" : "text-credit"}`}>
                    {r.balance > 0 ? `${rupees(r.balance)} still to pay` : r.balance < 0 ? `${rupees(-r.balance)} refund` : "Nothing due"}
                  </div>
                  {best && <span className="chip chip-ok mt-2">Lower tax</span>}
                </div>
              );
            })}
          </div>

          {est.notes.length > 0 && (
            <ul className="card mt-3 space-y-1.5 p-4 text-[13px]">
              {est.notes.map((x, i) => (
                <li key={i} className={x.includes("EXCLUDED") || x.includes("not yet verified") ? "text-warn font-medium" : "text-ink-2"}>
                  • {x}
                </li>
              ))}
            </ul>
          )}

          <section className="card mt-3 overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Computation</th>
                  <th className="text-right">New</th>
                  <th className="text-right">Old</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((l) => {
                  const a = byN[l];
                  const b = byO[l];
                  const kind = (a ?? b).kind;
                  return (
                    <tr key={l} className={kind === "grand" ? "bg-surface-2 font-semibold" : kind === "total" ? "font-semibold" : ""}>
                      <td>
                        {l}
                        {(a ?? b).source && <div className="text-ink-3 text-[11.5px] font-normal">{(a ?? b).source}</div>}
                      </td>
                      <td className="num text-right">{a ? rupees(a.amount) : "—"}</td>
                      <td className="num text-right">{b ? rupees(b.amount) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </>
  );
}

type Row = Record<string, string | number>;
function EntryList<R extends Row & { amount: number }>({
  title,
  sub,
  rows,
  onChange,
  blank,
  render,
}: {
  title: string;
  sub?: string;
  rows: R[];
  onChange: (rows: R[]) => void;
  blank: R;
  render: (r: R, set: (r: R) => void) => React.ReactNode;
}) {
  const total = rows.reduce((a, r) => a + (Number(r.amount) || 0), 0);
  return (
    <section className="card p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[14px] font-semibold">{title}</h2>
        <span className="num text-ink-2 text-[13px]">{rupees(total)}</span>
      </div>
      {sub && <p className="text-ink-3 mt-0.5 text-[12px]">{sub}</p>}
      <div className="mt-3 space-y-2">
        {rows.map((r, i) => {
          const set = (nr: R) => onChange(rows.map((x, j) => (j === i ? nr : x)));
          return (
            <div key={i} className="flex flex-wrap gap-2">
              {render(r, set)}
              <input
                className="input num w-32"
                inputMode="decimal"
                placeholder="Amount"
                value={r.amount || ""}
                onChange={(e) => set({ ...r, amount: Number(e.target.value.replace(/[,₹\s]/g, "")) || 0 })}
              />
              <button className="btn btn-ghost btn-sm self-center" onClick={() => onChange(rows.filter((_, j) => j !== i))} aria-label="Remove">
                Remove
              </button>
            </div>
          );
        })}
        <button className="btn btn-sm" onClick={() => onChange([...rows, { ...blank }])}>
          Add entry
        </button>
      </div>
    </section>
  );
}
