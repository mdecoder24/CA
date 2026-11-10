"use client";

import { useState } from "react";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Category, type Rule } from "@/lib/api";
import { useData } from "@/lib/use-data";

const blank = { pattern: "", match_type: "contains", direction: "credit", category_id: 0, priority: 50, auto_confirm: false, enabled: true };

export default function RulesPage() {
  const { toast, bump } = useApp();
  const { data: rules, reload } = useData(() => api.get<Rule[]>("/api/rules"), []);
  const { data: cats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const [draft, setDraft] = useState({ ...blank });
  const catName = (id: number) => cats?.find((c) => c.id === id)?.name ?? "?";

  const save = async (r: Partial<Rule> & { id?: number }) => {
    try {
      const body = { ...blank, ...r, min_amount: r.min_amount ?? null, max_amount: r.max_amount ?? null };
      if (r.id) await api.send("PUT", `/api/rules/${r.id}`, body);
      else await api.send("POST", "/api/rules", body);
      reload();
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    }
  };

  const rerun = async () => {
    const r = await api.send<{ changed: number }>("POST", "/api/rules/rerun");
    toast(`Rules re-applied. ${r.changed} transactions changed. Confirmed ones are never touched.`);
    bump();
  };

  return (
    <>
      <PageHeader
        title="Rules"
        sub="Rules match the original bank narration. Lower priority runs first. Rule results are suggestions unless auto-confirm is on."
        actions={
          <button className="btn" onClick={rerun}>
            Re-run on unconfirmed
          </button>
        }
      />

      <form
        className="card mb-4 flex flex-wrap items-end gap-2 p-4"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await save(draft as Partial<Rule>)) setDraft({ ...blank });
        }}
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="label">Narration contains</span>
          <input className="input" value={draft.pattern} onChange={(e) => setDraft({ ...draft, pattern: e.target.value })} placeholder="e.g. ACME TECHNOLOGIES" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Match</span>
          <select className="select" value={draft.match_type} onChange={(e) => setDraft({ ...draft, match_type: e.target.value })}>
            <option value="contains">contains</option>
            <option value="regex">regex</option>
            <option value="exact">exact payer</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Direction</span>
          <select
            className="select"
            value={draft.direction}
            onChange={(e) => setDraft({ ...draft, direction: e.target.value, category_id: 0 })}
          >
            <option value="credit">Credit</option>
            <option value="debit">Debit</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Category</span>
          <select className="select w-56" value={draft.category_id || ""} onChange={(e) => setDraft({ ...draft, category_id: Number(e.target.value) })}>
            <option value="" disabled>
              Choose…
            </option>
            {cats
              ?.filter((c) => c.direction === draft.direction)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 self-center text-[13px]">
          <input type="checkbox" checked={draft.auto_confirm} onChange={(e) => setDraft({ ...draft, auto_confirm: e.target.checked })} />
          Auto-confirm
        </label>
        <button className="btn btn-primary" disabled={!draft.pattern.trim() || !draft.category_id}>
          Add rule
        </button>
      </form>

      <section className="card overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th className="w-20">Priority</th>
              <th>Pattern</th>
              <th>Dir.</th>
              <th>Category</th>
              <th>Auto</th>
              <th>On</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rules?.map((r) => (
              <tr key={r.id} className={r.enabled ? "" : "opacity-50"}>
                <td>
                  <input
                    className="input num h-7 w-16"
                    defaultValue={r.priority}
                    onBlur={(e) => Number(e.target.value) !== r.priority && save({ ...r, priority: Number(e.target.value) || r.priority })}
                    aria-label="Priority"
                  />
                </td>
                <td className="max-w-96">
                  <code className="text-[12px] break-all">{r.pattern}</code>
                  <div className="text-ink-3 text-[11.5px]">
                    {r.match_type}
                    {r.builtin && " · built-in"}
                  </div>
                </td>
                <td className="text-ink-2">{r.direction}</td>
                <td>{catName(r.category_id)}</td>
                <td>
                  <input type="checkbox" checked={r.auto_confirm} onChange={(e) => save({ ...r, auto_confirm: e.target.checked })} aria-label="Auto-confirm" />
                </td>
                <td>
                  <input type="checkbox" checked={r.enabled} onChange={(e) => save({ ...r, enabled: e.target.checked })} aria-label="Enabled" />
                </td>
                <td>
                  <button
                    className="btn btn-ghost btn-sm text-danger"
                    onClick={async () => {
                      await api.send("DELETE", `/api/rules/${r.id}`);
                      reload();
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
