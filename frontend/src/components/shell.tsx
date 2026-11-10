"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Toast = { id: number; text: string; tone: "ok" | "error" };
type Ctx = {
  fy: string;
  fys: string[];
  setFy: (fy: string) => void;
  toast: (text: string, tone?: "ok" | "error") => void;
  version: number;
  bump: () => void;
  backendDown: boolean;
};

const AppCtx = createContext<Ctx | null>(null);
export const useApp = () => {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/review", label: "Review" },
  { href: "/transactions", label: "Transactions" },
  { href: "/imports", label: "Imports" },
  { href: "/tax", label: "Tax estimate" },
  { href: "/reports", label: "CA pack" },
  { href: "/rules", label: "Rules" },
  { href: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [fy, setFyState] = useState("");
  const [fys, setFys] = useState<string[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [version, setVersion] = useState(0);
  const [backendDown, setBackendDown] = useState(false);
  const nextId = useRef(1);

  const bump = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    api
      .get<{ fys: string[]; default_fy: string }>("/api/meta")
      .then((m) => {
        setBackendDown(false);
        setFys(m.fys);
        let saved = "";
        try {
          saved = localStorage.getItem("fintrack.fy") ?? "";
        } catch {}
        setFyState(saved && m.fys.includes(saved) ? saved : m.default_fy);
      })
      .catch(() => setBackendDown(true));
  }, [version]);

  const setFy = (v: string) => {
    setFyState(v);
    try {
      localStorage.setItem("fintrack.fy", v);
    } catch {}
  };

  const toast = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-2), { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 6000 : 3200);
  }, []);

  return (
    <AppCtx.Provider value={{ fy, fys, setFy, toast, version, bump, backendDown }}>
      <div className="flex min-h-dvh flex-col md:flex-row">
        <aside className="border-line bg-surface md:sticky md:top-0 md:h-dvh md:w-56 md:shrink-0 md:border-r border-b md:border-b-0">
          <div className="flex items-center justify-between gap-3 px-4 py-3 md:block md:px-5 md:py-5">
            <div>
              <div className="text-[15px] font-semibold tracking-tight">FinTrack</div>
              <div className="text-ink-3 text-[11.5px]">Personal finance · India</div>
            </div>
            <label className="md:mt-5 md:block">
              <span className="label hidden md:block md:mb-1">Financial year</span>
              <select
                className="select w-36 md:w-full"
                value={fy}
                onChange={(e) => setFy(e.target.value)}
                aria-label="Financial year"
              >
                {fys.map((y) => (
                  <option key={y} value={y}>
                    FY {y}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:px-3">
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={`shrink-0 rounded-lg px-3 py-1.5 text-[13.5px] ${
                    active ? "bg-accent-soft text-accent font-semibold" : "text-ink-2 hover:bg-surface-2"
                  }`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <p className="text-ink-3 hidden px-5 pt-4 text-[11px] leading-relaxed md:block">
            Runs on this computer only. Bank data never leaves it.
          </p>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-5 md:px-8 md:py-7">
          {backendDown ? (
            <div className="card mx-auto mt-10 max-w-lg p-6">
              <h1 className="text-lg font-semibold">Backend not running</h1>
              <p className="text-ink-2 mt-2 text-sm">
                Start everything from the project folder with <code className="bg-surface-2 rounded px-1">./dev.sh</code>, then
                reload this page.
              </p>
              <button className="btn mt-4" onClick={bump}>
                Retry
              </button>
            </div>
          ) : fy ? (
            children
          ) : null}
        </main>
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast pointer-events-auto max-w-md rounded-lg px-4 py-2.5 text-[13.5px] shadow-lg ${
              t.tone === "error" ? "bg-danger text-white" : "bg-ink text-bg"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </AppCtx.Provider>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {sub && <p className="text-ink-2 mt-0.5 text-[13.5px]">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, tone, hint }: { label: string; value: React.ReactNode; tone?: "credit" | "warn"; hint?: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-ink-3 text-[12px] font-medium">{label}</div>
      <div className={`num mt-1 text-[20px] font-semibold tracking-tight ${tone === "credit" ? "text-credit" : tone === "warn" ? "text-warn" : ""}`}>
        {value}
      </div>
      {hint && <div className="text-ink-3 mt-1 text-[12px]">{hint}</div>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <div className="font-semibold">{title}</div>
      {children && <div className="text-ink-2 mt-1 text-sm">{children}</div>}
    </div>
  );
}
