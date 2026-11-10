"use client";

import { useState } from "react";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Category } from "@/lib/api";
import { useData } from "@/lib/use-data";

type Settings = {
  anomaly: { large_credit_paise: number; round_repeat_min: number; round_unit_paise: number };
  ollama: { enabled: boolean; url: string; model: string };
};

const TREATMENTS: [string, string][] = [
  ["salary", "Salary income"],
  ["profession", "Freelance / professional income"],
  ["interest_savings", "Savings interest"],
  ["interest_other", "Other interest"],
  ["dividend", "Dividend"],
  ["other_income", "Other income"],
  ["gift_relative", "Gift from relative (exempt)"],
  ["gift_nonrelative", "Gift from non-relative"],
  ["trading_capital", "Trading money movement (not income)"],
  ["not_income", "Not income"],
  ["unexplained", "Needs explanation"],
  ["business_expense", "Business expense"],
  ["tax_paid", "Tax payment"],
  ["expense", "Personal expense"],
];

export default function SettingsPage() {
  const { data } = useData(() => api.get<Settings>("/api/settings"), []);
  return data ? <SettingsForm initial={data} /> : null;
}

function SettingsForm({ initial }: { initial: Settings }) {
  const { toast, bump } = useApp();
  const { data: cats, reload: reloadCats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const [s, setS] = useState<Settings>(initial);
  const [newCat, setNewCat] = useState({ name: "", direction: "credit", treatment: "other_income" });
  const [backupDir, setBackupDir] = useState("");

  const put = async (key: keyof Settings) => {
    try {
      await api.send("PUT", `/api/settings/${key}`, s[key]);
      toast("Saved.");
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Flags</h2>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="label">Large credit from (₹)</span>
              <input
                className="input num"
                value={s.anomaly.large_credit_paise / 100}
                onChange={(e) => setS({ ...s, anomaly: { ...s.anomaly, large_credit_paise: (Number(e.target.value) || 0) * 100 } })}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="label">Repeated round amount, times</span>
              <input
                className="input num"
                value={s.anomaly.round_repeat_min}
                onChange={(e) => setS({ ...s, anomaly: { ...s.anomaly, round_repeat_min: Number(e.target.value) || 3 } })}
              />
            </label>
          </div>
          <button className="btn mt-3" onClick={() => put("anomaly")}>
            Save & re-check
          </button>
        </section>

        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Local AI (optional, free)</h2>
          <p className="text-ink-2 mt-1 text-[12.5px]">
            Uses <a className="underline" href="https://ollama.com" target="_blank" rel="noreferrer">Ollama</a> on this computer to suggest
            categories. Install it, then run <code className="bg-surface-2 rounded px-1">ollama pull {s.ollama.model}</code>. Nothing is sent to the internet.
            Suggestions always need your confirmation.
          </p>
          <label className="mt-3 flex items-center gap-2 text-[13.5px]">
            <input type="checkbox" checked={s.ollama.enabled} onChange={(e) => setS({ ...s, ollama: { ...s.ollama, enabled: e.target.checked } })} />
            Enabled
          </label>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="label">Model</span>
              <input className="input" value={s.ollama.model} onChange={(e) => setS({ ...s, ollama: { ...s.ollama, model: e.target.value } })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="label">URL</span>
              <input className="input" value={s.ollama.url} onChange={(e) => setS({ ...s, ollama: { ...s.ollama, url: e.target.value } })} />
            </label>
          </div>
          <button className="btn mt-3" onClick={() => put("ollama")}>
            Save
          </button>
        </section>

        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Categories</h2>
          <form
            className="mt-3 flex flex-wrap gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api.send("POST", "/api/categories", newCat);
                setNewCat({ ...newCat, name: "" });
                reloadCats();
              } catch (err) {
                toast((err as Error).message, "error");
              }
            }}
          >
            <input className="input min-w-0 flex-1" placeholder="New category name" value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} />
            <select className="select" value={newCat.direction} onChange={(e) => setNewCat({ ...newCat, direction: e.target.value })}>
              <option value="credit">Credit</option>
              <option value="debit">Debit</option>
            </select>
            <select className="select" value={newCat.treatment} onChange={(e) => setNewCat({ ...newCat, treatment: e.target.value })} aria-label="Tax treatment">
              {TREATMENTS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <button className="btn" disabled={!newCat.name.trim()}>
              Add
            </button>
          </form>
          <div className="mt-3 max-h-72 overflow-auto">
            <table className="table">
              <tbody>
                {cats?.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="text-ink-3">{c.direction}</td>
                    <td className="text-ink-3">{TREATMENTS.find(([v]) => v === c.treatment)?.[1]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="text-[14px] font-semibold">Backup & privacy</h2>
          <p className="text-ink-2 mt-1 text-[12.5px]">
            All data is in the <code className="bg-surface-2 rounded px-1">data/</code> folder of the project. Turn on FileVault (System Settings → Privacy &
            Security) so it is encrypted on disk.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              className="input min-w-0 flex-1"
              placeholder="Backup folder (default: data/backups)"
              value={backupDir}
              onChange={(e) => setBackupDir(e.target.value)}
            />
            <button
              className="btn"
              onClick={async () => {
                try {
                  const r = await api.send<{ path: string }>("POST", "/api/backup", { folder: backupDir || null });
                  toast(`Backed up to ${r.path}`);
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Back up now
            </button>
          </div>
        </section>
      </div>
    </>
  );
}
