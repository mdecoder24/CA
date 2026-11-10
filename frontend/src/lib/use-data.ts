"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/shell";

/** Fetch on mount and whenever deps or the global data version change. */
export function useData<T>(load: () => Promise<T>, deps: unknown[]) {
  const { version } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    load()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, tick]);

  return { data, error, reload, setData };
}
