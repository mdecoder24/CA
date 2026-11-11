"use client";

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="bg-surface-2 inline-flex rounded-lg p-0.5" role="tablist">
      {options.map(([v, label]) => (
        <button
          key={v}
          role="tab"
          aria-selected={value === v}
          className={`rounded-md px-3 py-1 text-[12.5px] font-medium ${value === v ? "bg-surface shadow-sm" : "text-ink-2"}`}
          onClick={() => onChange(v)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
