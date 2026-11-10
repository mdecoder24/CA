export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Required by the backend on every write (CSRF guard).
const APP_HEADER = { "X-FinTrack": "1" };

export class ApiError extends Error {
  code?: string;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (r.ok) return r.json() as Promise<T>;
  let msg = `Request failed (${r.status})`;
  let code: string | undefined;
  try {
    const body = await r.json();
    const d = body.detail;
    if (typeof d === "string") msg = d;
    else if (d && typeof d === "object") {
      msg = d.message ?? msg;
      code = d.code;
    }
  } catch {}
  throw new ApiError(msg, r.status, code);
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
    const qs = params
      ? "?" +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    return fetch(`${API}${path}${qs}`, { cache: "no-store" }).then((r) => handle<T>(r));
  },
  send: <T>(method: string, path: string, body?: unknown) =>
    fetch(`${API}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json", ...APP_HEADER } : APP_HEADER,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then((r) => handle<T>(r)),
  upload: <T>(path: string, form: FormData) =>
    fetch(`${API}${path}`, { method: "POST", body: form, headers: APP_HEADER }).then((r) => handle<T>(r)),
  async download(path: string) {
    const r = await fetch(`${API}${path}`, { method: "POST", headers: APP_HEADER });
    if (!r.ok) await handle(r);
    const blob = await r.blob();
    const cd = r.headers.get("content-disposition") ?? "";
    const name = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)?.[1] ?? "export";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = decodeURIComponent(name);
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return decodeURIComponent(name);
  },
};

// ---------- types
export type Flag = { id: number; type: string; detail: string; resolved: boolean; resolution_note: string };
export type Txn = {
  id: number;
  txn_date: string;
  value_date: string | null;
  raw_description: string;
  ref_no: string;
  debit: number;
  credit: number;
  balance: number | null;
  direction: "credit" | "debit";
  category_id: number | null;
  category: string | null;
  treatment: string | null;
  status: "unclassified" | "suggested" | "confirmed";
  source: string;
  confidence: number | null;
  note: string;
  nature: string;
  counterparty: string;
  flags: Flag[];
};
export type Category = { id: number; name: string; direction: "credit" | "debit"; treatment: string; sort: number };
export type Rule = {
  id: number;
  priority: number;
  match_type: "contains" | "regex" | "exact";
  pattern: string;
  direction: "credit" | "debit" | "any";
  min_amount: number | null;
  max_amount: number | null;
  category_id: number;
  auto_confirm: boolean;
  builtin: boolean;
  enabled: boolean;
};
export type ImportBatch = {
  id: number;
  filename: string;
  sha256: string;
  file_type: string;
  period_from: string | null;
  period_to: string | null;
  opening_balance: number | null;
  closing_balance: number | null;
  rows_parsed: number;
  rows_inserted: number;
  rows_duplicate: number;
  status: string;
  reconcile_detail: string;
  override_reason: string;
  created_at: string;
};
export type Dashboard = {
  fy: string;
  total_credits: number;
  total_debits: number;
  closing_balance: number | null;
  txn_count: number;
  unclassified_credits: number;
  unclassified_credit_amount: number;
  unclassified_debits: number;
  open_flags: number;
  monthly: { month: string; credits: number; debits: number }[];
  income_heads: { head: string; amount: number }[];
  credit_categories: { category: string; amount: number }[];
  gaps: { from: string; to: string }[];
};
export type TaxLine = { label: string; amount: number; source: string; kind: "row" | "total" | "grand" };
export type TaxEstimate = {
  fy: string;
  label: string;
  act: string;
  verified: boolean;
  regimes: Record<"new" | "old", { name: string; lines: TaxLine[]; total_income: number; liability: number; balance: number }>;
  recommended: "new" | "old";
  notes: string[];
  salary_bank_net: number;
  tds_total: number;
  taxes_paid_total: number;
  disclaimer: string;
};

// ---------- formatting (Indian grouping)
const inrFmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2, minimumFractionDigits: 2 });
const inrWhole = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

/** paise -> "₹1,34,550.00" */
export const paise = (p: number | null | undefined, whole = false) =>
  p === null || p === undefined ? "—" : (whole ? inrWhole : inrFmt).format(p / 100);
/** rupees -> "₹1,34,550" */
export const rupees = (r: number | null | undefined) => (r === null || r === undefined ? "—" : inrWhole.format(r));

export const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
};
export const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "short" });
};
