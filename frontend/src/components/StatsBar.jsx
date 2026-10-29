import { useEffect, useState } from "react";
import { api } from "../api";

export default function StatsBar({ refreshKey }) {
  const [s, setS] = useState(null);
  useEffect(() => {
    let stop = false;
    const load = () => api.stats().then((d) => !stop && setS(d)).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [refreshKey]);
  if (!s) return null;
  const c = s.counts || {};
  const pct = (x) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
  return (
    <div className="stats">
      <span>{s.total} documents</span>
      <span className="ok">{c.completed || 0} completed</span>
      <span className="warn">{c.needs_review || 0} need review</span>
      <span className="bad">{c.failed || 0} failed</span>
      <span>success {pct(s.success_rate)}</span>
      <span>median {s.processing_seconds?.p50 ?? "–"}s</span>
    </div>
  );
}
