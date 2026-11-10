"use client";

import type { Category } from "@/lib/api";

export function CategorySelect({
  categories,
  direction,
  value,
  onChange,
  className = "",
  id,
}: {
  categories: Category[];
  direction: "credit" | "debit";
  value: number | null;
  onChange: (id: number) => void;
  className?: string;
  id?: string;
}) {
  return (
    <select
      id={id}
      className={`select ${className}`}
      value={value ?? ""}
      onChange={(e) => e.target.value && onChange(Number(e.target.value))}
      aria-label="Category"
    >
      <option value="" disabled>
        Choose category…
      </option>
      {categories
        .filter((c) => c.direction === direction)
        .map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
    </select>
  );
}

export function StatusChip({ status, source }: { status: string; source?: string }) {
  if (status === "confirmed") return <span className="chip chip-ok">Confirmed</span>;
  if (status === "suggested")
    return <span className="chip chip-warn">Suggested{source === "llm" ? " · AI" : source === "rule" ? " · rule" : ""}</span>;
  return <span className="chip">Unclassified</span>;
}
