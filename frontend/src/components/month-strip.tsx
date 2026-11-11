"use client";

import { compactInr } from "@/components/shell";

export type MonthStat = { month: string; credit: number; debit: number; count: number };

export function monthTitle(ym: string, style: "long" | "short" = "long") {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: style, year: "numeric" });
}

/** Totals per calendar month, in date order. */
export function monthStats<T>(rows: T[], date: (r: T) => string, credit: (r: T) => number, debit: (r: T) => number): MonthStat[] {
  const map = new Map<string, MonthStat>();
  for (const r of rows) {
    const m = date(r).slice(0, 7);
    const s = map.get(m) ?? { month: m, credit: 0, debit: 0, count: 0 };
    s.credit += credit(r);
    s.debit += debit(r);
    s.count += 1;
    map.set(m, s);
  }
  return [...map.values()].sort((a, b) => a.month.localeCompare(b.month));
}

/** Horizontal month picker: one chip per month with its money in / out. "" means all months. */
export function MonthStrip({ months, value, onChange }: { months: MonthStat[]; value: string; onChange: (m: string) => void }) {
  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Month">
      <Chip active={value === ""} onClick={() => onChange("")}>
        <div className="text-[13px] font-semibold">All months</div>
        <div className="text-ink-3 text-[11.5px]">{months.reduce((a, m) => a + m.count, 0)} entries</div>
      </Chip>
      {months.map((m) => (
        <Chip key={m.month} active={value === m.month} onClick={() => onChange(m.month)}>
          <div className="text-[13px] font-semibold">{monthTitle(m.month, "short")}</div>
          <div className="num text-[11.5px]">
            <span className="text-credit">+{compactInr(m.credit)}</span> <span className="text-ink-2">−{compactInr(m.debit)}</span>
          </div>
          <div className="text-ink-3 text-[11px]">{m.count} entries</div>
        </Chip>
      ))}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`btn h-auto shrink-0 flex-col items-start gap-0 px-3 py-2 text-left ${active ? "border-accent bg-accent-soft ring-accent ring-1" : ""}`}
    >
      {children}
    </button>
  );
}
