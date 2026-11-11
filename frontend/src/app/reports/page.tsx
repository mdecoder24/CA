"use client";

import { useState } from "react";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Dashboard, paise } from "@/lib/api";
import { useData } from "@/lib/use-data";

const SHEETS = [
  "Summary",
  "All transactions (original narration + classification side by side)",
  "Credits by category · Debits by category",
  "Income by head",
  "Interest",
  "Trading flows (to / from broker, net)",
  "Cash deposits",
  "Flagged & unexplained credits with your notes",
  "Tax estimate, old vs new regime",
  "Import log with file hashes (audit trail)",
];

export default function ReportsPage() {
  const { fy, toast } = useApp();
  const { data: d } = useData(() => api.get<Dashboard>("/api/dashboard", { fy }), [fy]);
  const [busy, setBusy] = useState<string | null>(null);

  const get = async (kind: "excel" | "pdf") => {
    setBusy(kind);
    try {
      const name = await api.download(`/api/reports/${fy}/${kind}`);
      toast(`Downloaded ${name}. A copy is also saved in data/exports.`);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="CA pack"
        sub={`Everything your CA needs for FY ${fy}, in one workbook plus a short PDF summary. Always covers all bank accounts.`}
      />

      {d && (d.unclassified_credits > 0 || d.open_flags > 0 || d.gaps.length > 0) && (
        <div className="bg-warn-soft text-warn mb-4 rounded-lg px-4 py-3 text-[13.5px]">
          Before you send this:{" "}
          {[
            d.unclassified_credits > 0 && `${d.unclassified_credits} credits (${paise(d.unclassified_credit_amount, true)}) are not confirmed`,
            d.open_flags > 0 && `${d.open_flags} flags are open`,
            d.gaps.length > 0 && `${d.gaps.length} statement gap(s)`,
          ]
            .filter(Boolean)
            .join(" · ")}
          . The pack lists them, so you can still export.
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <section className="card p-5">
          <h2 className="font-semibold">Excel workbook</h2>
          <ul className="text-ink-2 mt-2 list-disc space-y-0.5 pl-5 text-[13px]">
            {SHEETS.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <button className="btn btn-primary mt-4" onClick={() => get("excel")} disabled={busy !== null}>
            {busy === "excel" ? "Building…" : "Download .xlsx"}
          </button>
        </section>
        <section className="card p-5">
          <h2 className="font-semibold">PDF summary</h2>
          <p className="text-ink-2 mt-2 text-[13px]">
            2–4 pages: totals, income by head, the tax estimate for both regimes, and every credit that still needs an explanation.
          </p>
          <button className="btn btn-primary mt-4" onClick={() => get("pdf")} disabled={busy !== null}>
            {busy === "pdf" ? "Building…" : "Download .pdf"}
          </button>
        </section>
      </div>
    </>
  );
}
