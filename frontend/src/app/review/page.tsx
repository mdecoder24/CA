"use client";

import { useEffect, useRef, useState } from "react";
import { CategorySelect, StatusChip } from "@/components/category-select";
import { Empty, PageHeader, useApp } from "@/components/shell";
import { api, type Category, fmtDate, paise, type Txn } from "@/lib/api";
import { useData } from "@/lib/use-data";

const FLAG_LABEL: Record<string, string> = {
  large_credit: "Large credit",
  cash_deposit: "Cash deposit",
  possible_duplicate: "Possible duplicate",
  round_repeat: "Repeated round amount",
};

export default function ReviewPage() {
  const { fy, toast, bump, accountId } = useApp();
  const [direction, setDirection] = useState<"credit" | "debit">("credit");
  const { data: items, reload } = useData(() => api.get<Txn[]>("/api/review", { fy, direction, account_id: accountId }), [fy, direction, accountId]);
  const { data: cats } = useData(() => api.get<Category[]>("/api/categories"), []);
  const [active, setActive] = useState(0);
  const [aiBusy, setAiBusy] = useState(false);

  const [scope, setScope] = useState(`${fy}|${direction}`);
  if (scope !== `${fy}|${direction}`) {
    setScope(`${fy}|${direction}`);
    setActive(0);
  }

  // j / k to move between items. No animation: this is used constantly.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return;
      if (!items?.length) return;
      if (e.key === "j") setActive((a) => Math.min(a + 1, items.length - 1));
      if (e.key === "k") setActive((a) => Math.max(a - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items]);

  const after = () => {
    reload();
    bump();
  };

  const suggest = async () => {
    setAiBusy(true);
    try {
      const r = await api.send<{ ok: boolean; message: string }>("POST", "/api/ai/suggest");
      toast(r.message, r.ok ? "ok" : "error");
      after();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setAiBusy(false);
    }
  };

  const confirmAllSuggested = async () => {
    const ids = (items ?? []).filter((i) => i.status === "suggested" && !i.flags.some((f) => !f.resolved)).map((i) => i.id);
    if (!ids.length) return;
    const r = await api.send<{ updated: number }>("POST", "/api/transactions/bulk-classify", { ids, confirm: true });
    toast(`Confirmed ${r.updated} suggestions.`);
    after();
  };

  const suggestedCount = items?.filter((i) => i.status === "suggested" && !i.flags.some((f) => !f.resolved)).length ?? 0;

  return (
    <>
      <PageHeader
        title="Review"
        sub="Confirm what each transaction was. Only confirmed credits count towards income."
        actions={
          <>
            <button className="btn" onClick={suggest} disabled={aiBusy}>
              {aiBusy ? "Asking local AI…" : "Suggest with local AI"}
            </button>
            <button className="btn" onClick={confirmAllSuggested} disabled={!suggestedCount}>
              {suggestedCount ? `Confirm ${suggestedCount} unflagged suggestions` : "No unflagged suggestions"}
            </button>
          </>
        }
      />

      <div className="mb-4 flex items-center gap-3">
        <div className="bg-surface-2 inline-flex rounded-lg p-0.5" role="tablist">
          {(["credit", "debit"] as const).map((d) => (
            <button
              key={d}
              role="tab"
              aria-selected={direction === d}
              className={`rounded-md px-3 py-1 text-[13px] font-medium ${direction === d ? "bg-surface shadow-sm" : "text-ink-2"}`}
              onClick={() => setDirection(d)}
            >
              {d === "credit" ? "Credits (money in)" : "Debits (money out)"}
            </button>
          ))}
        </div>
        <span className="text-ink-3 hidden text-[12px] sm:inline">
          <kbd>j</kbd>/<kbd>k</kbd> to move · <kbd>Enter</kbd> in a card to confirm
        </span>
      </div>

      {items && items.length === 0 && (
        <Empty title="All caught up">Every {direction} in FY {fy} is confirmed and no flags are open.</Empty>
      )}

      <div className="space-y-2.5">
        {items?.map((t, i) => (
          <ReviewCard
            key={`${t.id}-${t.category_id}-${t.status}`}
            t={t}
            cats={cats ?? []}
            active={i === active}
            onFocus={() => setActive(i)}
            onDone={after}
          />
        ))}
      </div>
    </>
  );
}

function ReviewCard({
  t,
  cats,
  active,
  onFocus,
  onDone,
}: {
  t: Txn;
  cats: Category[];
  active: boolean;
  onFocus: () => void;
  onDone: () => void;
}) {
  const { toast } = useApp();
  const ref = useRef<HTMLDivElement>(null);
  const [cat, setCat] = useState<number | null>(t.category_id);
  const [note, setNote] = useState(t.note);
  const [makeRule, setMakeRule] = useState(false);
  const [busy, setBusy] = useState(false);
  const openFlags = t.flags.filter((f) => !f.resolved);
  const [flagNotes, setFlagNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const save = async () => {
    if (!cat) return;
    setBusy(true);
    try {
      for (const f of openFlags) {
        const n = flagNotes[f.id]?.trim();
        if (n) await api.send("PATCH", `/api/flags/${f.id}`, { resolved: true, resolution_note: n });
      }
      const r = await api.send<{ rule_id: number | null }>("PATCH", `/api/transactions/${t.id}/classification`, {
        category_id: cat,
        note,
        confirm: true,
        make_rule: makeRule,
      });
      toast(r.rule_id ? `Confirmed. Rule created for “${t.counterparty}”.` : "Confirmed.");
      onDone();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const amount = t.credit || t.debit;
  return (
    <div
      ref={ref}
      onFocusCapture={onFocus}
      onClick={onFocus}
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "TEXTAREA" && (e.target as HTMLElement).tagName !== "BUTTON") {
          e.preventDefault();
          save();
        }
      }}
      className={`card p-4 ${active ? "ring-accent ring-2" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0 flex-1">
          <div className="text-ink-3 num text-[12px]">
            {fmtDate(t.txn_date)}
            {t.ref_no && <> · {t.ref_no}</>}
            {t.counterparty && <> · {t.counterparty}</>}
          </div>
          <div className="mt-0.5 font-mono text-[13px] break-words">{t.raw_description}</div>
        </div>
        <div className="text-right">
          <div className={`num text-[17px] font-semibold ${t.credit ? "text-credit" : ""}`}>
            {t.credit ? "+" : "−"}
            {paise(amount)}
          </div>
          <StatusChip status={t.status} source={t.source} />
        </div>
      </div>

      {openFlags.length > 0 && (
        <ul className="mt-3 space-y-2">
          {openFlags.map((f) => (
            <li key={f.id} className="bg-surface-2 rounded-lg px-3 py-2">
              <div className="text-warn flex items-center gap-1.5 text-[12px] font-semibold">
                <span className="bg-warn inline-block size-1.5 rounded-full" aria-hidden />
                {FLAG_LABEL[f.type] ?? f.type}
              </div>
              <div className="text-ink-2 text-[12.5px]">{f.detail}</div>
              <input
                className="input mt-1.5 h-8 w-full"
                placeholder="Explain where this came from (optional)"
                value={flagNotes[f.id] ?? ""}
                onChange={(e) => setFlagNotes({ ...flagNotes, [f.id]: e.target.value })}
              />
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CategorySelect categories={cats} direction={t.direction} value={cat} onChange={setCat} className="w-full sm:w-64" />
        <input
          className="input min-w-0 flex-1"
          placeholder="Note for your CA (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {t.counterparty && (
          <label className="text-ink-2 flex items-center gap-1.5 text-[12.5px]">
            <input type="checkbox" checked={makeRule} onChange={(e) => setMakeRule(e.target.checked)} />
            Always for “{t.counterparty}”
          </label>
        )}
        <button className="btn btn-primary" onClick={save} disabled={!cat || busy}>
          Confirm
        </button>
      </div>
    </div>
  );
}
