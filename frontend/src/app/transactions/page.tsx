"use client";

import { useDeferredValue, useState } from "react";
import { CategorySelect, StatusChip } from "@/components/category-select";
import { PageHeader, useApp } from "@/components/shell";
import { api, type Category, fmtDate, paise, type Txn } from "@/lib/api";
import { useData } from "@/lib/use-data";

export default function TransactionsPage() {
  const { fy, toast, bump } = useApp();
  const [direction, setDirection] = useState("");
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [q, setQ] = useState("");
  const dq = useDeferredValue(q);
  const { data: cats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const { data: txs, reload } = useData(
    () => api.get<Txn[]>("/api/transactions", { fy, direction, status, category_id: categoryId, q: dq }),
    [fy, direction, status, categoryId, dq],
  );

  const setCat = async (t: Txn, id: number) => {
    try {
      await api.send("PATCH", `/api/transactions/${t.id}/classification`, { category_id: id, confirm: true });
      reload();
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const credits = txs?.reduce((a, t) => a + t.credit, 0) ?? 0;
  const debits = txs?.reduce((a, t) => a + t.debit, 0) ?? 0;

  return (
    <>
      <PageHeader title="Transactions" sub="Bank columns are the original statement data and cannot be edited. Classification is stored separately." />

      <div className="mb-3 flex flex-wrap gap-2">
        <input className="input w-full sm:w-64" placeholder="Search narration, ref, note…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="select" value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Direction">
          <option value="">In and out</option>
          <option value="credit">Credits</option>
          <option value="debit">Debits</option>
        </select>
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Any status</option>
          <option value="unconfirmed">Not confirmed</option>
          <option value="confirmed">Confirmed</option>
          <option value="suggested">Suggested</option>
          <option value="unclassified">Unclassified</option>
        </select>
        <select className="select max-w-56" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} aria-label="Category">
          <option value="">Any category</option>
          {cats?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.direction === "credit" ? "In · " : "Out · "}
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="text-ink-2 mb-2 text-[12.5px]">
        {txs?.length ?? 0} rows · in <span className="num text-credit">{paise(credits)}</span> · out <span className="num">{paise(debits)}</span>
      </div>

      <section className="card max-h-[calc(100dvh-220px)] overflow-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Narration (original)</th>
              <th className="text-right">Debit</th>
              <th className="text-right">Credit</th>
              <th className="text-right">Balance</th>
              <th>Category</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {txs?.map((t) => (
              <tr key={t.id}>
                <td className="num text-ink-2">{fmtDate(t.txn_date)}</td>
                <td className="min-w-64">
                  <div className="font-mono text-[12.5px] break-words">{t.raw_description}</div>
                  {(t.note || t.flags.some((f) => !f.resolved)) && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {t.flags
                        .filter((f) => !f.resolved)
                        .map((f) => (
                          <span key={f.id} className="chip chip-warn" title={f.detail}>
                            {f.type.replace("_", " ")}
                          </span>
                        ))}
                      {t.note && <span className="text-ink-2 text-[12px]">“{t.note}”</span>}
                    </div>
                  )}
                </td>
                <td className="num text-right">{t.debit ? paise(t.debit) : ""}</td>
                <td className="num text-credit text-right">{t.credit ? paise(t.credit) : ""}</td>
                <td className="num text-ink-2 text-right">{paise(t.balance)}</td>
                <td>
                  <CategorySelect
                    categories={cats ?? []}
                    direction={t.direction}
                    value={t.category_id}
                    onChange={(id) => setCat(t, id)}
                    className="h-8 w-52 text-[12.5px]"
                  />
                </td>
                <td>
                  <StatusChip status={t.status} source={t.source} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
