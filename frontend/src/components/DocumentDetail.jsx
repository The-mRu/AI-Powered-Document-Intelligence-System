import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { ACTIVE, FIELDS, GENERAL_FIELDS, PARTY_FIELDS, READY, friendly } from "../constants";
import Badge from "./Badge";

const ITEM_KEYS = ["description", "quantity", "unit", "unit_price", "line_total", "tax", "discount"];
const blankToNull = (v) => (v === "" || v === undefined ? null : v);
const normItem = (li) => Object.fromEntries(ITEM_KEYS.map((k) => [k, blankToNull(li[k] ?? null)]));

export default function DocumentDetail({ id, onChanged, onDeleted }) {
  const [doc, setDoc] = useState(null);
  const [result, setResult] = useState(null);
  const [pages, setPages] = useState([]);
  const [err, setErr] = useState(null);
  const [edit, setEdit] = useState(null); // null = read-only; object = editing draft
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    const d = await api.detail(id);
    setDoc(d);
    if (READY.includes(d.status)) {
      const [r, p] = await Promise.all([api.result(id), api.pages(id)]);
      setResult(r);
      setPages(p.items);
    } else {
      setResult(null);
      if (d.status === "failed") setPages((await api.pages(id)).items);
    }
    return d;
  }, [id]);

  useEffect(() => {
    setDoc(null);
    setResult(null);
    setPages([]);
    setEdit(null);
    setErr(null);
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const d = await load();
        if (!stop && ACTIVE.includes(d.status)) timer = setTimeout(tick, 1500);
      } catch (e) {
        if (!stop) setErr(e.message);
      }
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id, load]);

  if (err && !doc) return <section className="card"><p className="error">{err}</p></section>;
  if (!doc) return <section className="card"><p className="muted">Loading…</p></section>;

  const eff = result?.effective;

  function startEdit() {
    setErr(null);
    setEdit({
      fields: Object.fromEntries(FIELDS.map(([k]) => [k, eff[k]?.value ?? ""])),
      items: (eff.line_items || []).map((li) => Object.fromEntries(ITEM_KEYS.map((k) => [k, li[k] ?? ""]))),
      note: "",
    });
  }

  async function save() {
    const fields = {};
    FIELDS.forEach(([k]) => {
      const old = eff[k]?.value ?? "";
      if (edit.fields[k] !== old) fields[k] = edit.fields[k];
    });
    const newItems = edit.items.map(normItem);
    const itemsChanged = JSON.stringify(newItems) !== JSON.stringify((eff.line_items || []).map(normItem));
    if (!Object.keys(fields).length && !itemsChanged) {
      setErr("No changes to save");
      return;
    }
    const body = { fields, note: edit.note || null };
    if (itemsChanged) body.line_items = newItems;
    setSaving(true);
    setErr(null);
    try {
      setResult(await api.correct(id, body));
      await load();
      setEdit(null);
      onChanged?.();
    } catch (e) {
      setErr(e.message); // e.g. "'total' must be a plain decimal number"
    } finally {
      setSaving(false);
    }
  }

  async function act(fn) {
    setErr(null);
    try {
      await fn();
      await load();
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function removeDocument() {
    if (!deleting) {
      setDeleting(true);
      return;
    }
    setErr(null);
    try {
      await api.remove(id);
      onDeleted?.();
    } catch (e) {
      setDeleting(false);
      setErr(e.message);
    }
  }

  const issues = result?.validation?.issues ?? [];
  const order = { error: 0, warning: 1 };
  const problems = issues.filter((i) => i.severity !== "info").sort((a, b) => order[a.severity] - order[b.severity]);
  const checks = issues.filter((i) => i.severity === "info");
  const partySections = [
    ["Supplier / From", PARTY_FIELDS.supplier],
    ["Customer / Bill To", PARTY_FIELDS.customer],
    ["Shipping Recipient / Ship To", PARTY_FIELDS.shipping],
  ];

  return (
    <section className="card">
      <div className="row between">
        <div className="document-heading">
          <h2 className="ellipsis">{doc.filename}</h2>
          <Badge kind={doc.status}>{doc.status.replace("_", " ")}</Badge>
        </div>
        <button className={`delete-button ${deleting ? "confirm" : ""}`} onClick={removeDocument} disabled={doc.status === "processing"}>
          {deleting ? "Confirm delete" : "Delete document"}
        </button>
      </div>
      {deleting && <p className="delete-hint">This removes the stored file and all extracted data. Click again to confirm.</p>}
      <p className="muted">
        {doc.kind?.toUpperCase()} · {doc.progress?.page_count ?? "?"} page(s) · attempt {doc.attempts}
      </p>

      {ACTIVE.includes(doc.status) && (
        <div className="bar" role="progressbar" aria-valuenow={doc.progress?.percent ?? 0}>
          <div style={{ width: `${doc.progress?.percent ?? 5}%` }} />
        </div>
      )}
      {doc.warnings?.length > 0 && <p className="warn">{doc.warnings.join(" · ")}</p>}
      {err && <p className="error" role="alert">{err}</p>}

      {doc.status === "failed" && (
        <div className="callout bad">
          <strong>{friendly(doc.error_code)}</strong>
          <p>{doc.error_message}</p>
          <button onClick={() => act(() => api.reprocess(id))}>Reprocess</button>
        </div>
      )}

      {result && (
        <>
          <div className={`callout ${problems.length ? "warnbox" : "okbox"}`}>
            {problems.length ? (
              <>
                <strong>{problems.length} issue(s) need review</strong>
                <ul className="issues">
                  {problems.map((i, n) => (
                    <li key={n} className={i.severity}>
                      <Badge kind={i.severity} />
                      <span>{i.message}</span>
                      <small className="muted">{i.rule}{i.field ? ` · ${i.field}` : ""}</small>
                    </li>
                  ))}
                </ul>
                {doc.status === "needs_review" && (
                  <button className="ghost" onClick={() => act(() => api.approve(id))}>Approve as is</button>
                )}
              </>
            ) : (
              <strong>All validation checks passed</strong>
            )}
          </div>

          <div className="row between">
            <h3>Extracted data</h3>
            {edit ? (
              <div className="row">
                <button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save corrections"}</button>
                <button className="ghost" onClick={() => setEdit(null)} disabled={saving}>Cancel</button>
              </div>
            ) : (
              <button onClick={startEdit}>Edit values</button>
            )}
          </div>

          <div className="party-sections">
            {partySections.map(([title, fields]) => (
              <section key={title}>
                <h4>{title}</h4>
                <table className="grid">
                  <tbody>
                    {fields.map(([key, label]) => {
                      const f = eff[key] || {};
                      return (
                        <tr key={key}>
                          <td>{label}</td>
                          <td>{edit ? (
                            <input aria-label={`${title} ${label}`} value={edit.fields[key] ?? ""}
                              onChange={(e) => setEdit({ ...edit, fields: { ...edit.fields, [key]: e.target.value } })} />
                          ) : f.value ?? <span className="muted">— not found —</span>}</td>
                          <td><Badge kind={f.status || "missing"} />{f.flags?.map((fl) => <small key={fl} className="chip">{fl}</small>)}</td>
                          <td><small className="muted evidence">{f.evidence}</small></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>
            ))}
          </div>

          <table className="grid">
            <thead>
              <tr><th>Field</th><th>Value</th><th>Status</th><th>Evidence</th></tr>
            </thead>
            <tbody>
              {GENERAL_FIELDS.map(([k, label]) => {
                const f = eff[k] || {};
                return (
                  <tr key={k}>
                    <td>{label}</td>
                    <td>
                      {edit ? (
                        <input aria-label={label} value={edit.fields[k]} onChange={(e) => setEdit({ ...edit, fields: { ...edit.fields, [k]: e.target.value } })} />
                      ) : f.value ?? <span className="muted">— not found —</span>}
                    </td>
                    <td>
                      <Badge kind={f.status || "missing"} />
                      {f.flags?.map((fl) => <small key={fl} className="chip">{fl}</small>)}
                    </td>
                    <td><small className="muted evidence">{f.evidence}</small></td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <h3>Line items</h3>
          <table className="grid">
            <thead>
              <tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit price</th><th>Line total</th><th>Tax</th><th>Discount</th><th>Evidence</th>{edit && <th />}</tr>
            </thead>
            <tbody>
              {(edit ? edit.items : eff.line_items || []).map((li, n) => (
                <tr key={n} className={!edit && li.flags?.length ? "flagged" : ""}>
                  {ITEM_KEYS.map((k) => (
                    <td key={k}>
                      {edit ? (
                        <input aria-label={`${k} ${n + 1}`} value={li[k]} onChange={(e) => setEdit({ ...edit, items: edit.items.map((x, i) => (i === n ? { ...x, [k]: e.target.value } : x)) })} />
                      ) : li[k] ?? ""}
                    </td>
                  ))}
                  {!edit && (
                    <td>
                      <div className="line-evidence">
                        {ITEM_KEYS.map((field) => li[field] != null && (
                          <small key={field} className="muted evidence">
                            <strong>{field.replace("_", " ")}:</strong> {li[field]}
                          </small>
                        ))}
                        {li.evidence && (
                          <details>
                            <summary>Source row</summary>
                            <small className="muted evidence">{li.evidence}</small>
                          </details>
                        )}
                      </div>
                    </td>
                  )}
                  {edit && (
                    <td><button className="ghost" onClick={() => setEdit({ ...edit, items: edit.items.filter((_, i) => i !== n) })}>✕</button></td>
                  )}
                </tr>
              ))}
              {!(edit ? edit.items : eff.line_items || []).length && <tr><td colSpan={9} className="muted">No line items</td></tr>}
            </tbody>
          </table>
          {edit && (
            <div className="row">
              <button className="ghost" onClick={() => setEdit({ ...edit, items: [...edit.items, Object.fromEntries(ITEM_KEYS.map((k) => [k, ""]))] })}>+ Add line</button>
              <input placeholder="Note (optional, saved with the correction)" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
            </div>
          )}
          {result.corrections && <p className="muted">Manually corrected fields: {Object.keys(result.corrections.fields || {}).join(", ") || "line items"}. The original AI values are kept.</p>}

          {checks.length > 0 && (
            <details>
              <summary>{checks.length} check(s) passed</summary>
              <ul className="issues">{checks.map((i, n) => <li key={n}><Badge kind="info" /><span>{i.message}</span></li>)}</ul>
            </details>
          )}
        </>
      )}

      {pages.length > 0 && (
        <details>
          <summary>Extracted text ({pages.length} page{pages.length > 1 ? "s" : ""} shown)</summary>
          {pages.map((p) => (
            <div key={p.page_no}>
              <small className="muted">
                {p.label ? `Sheet ${p.label}` : `Page ${p.page_no}`} · {p.method}
                {p.confidence != null ? ` · OCR confidence ${Math.round(p.confidence)}%` : ""} · {p.duration_ms} ms
                {p.error ? ` · ERROR: ${p.error}` : ""}
              </small>
              <pre className="pagetext">{p.text}</pre>
            </div>
          ))}
        </details>
      )}

      {doc.history?.length > 0 && (
        <details>
          <summary>Processing history</summary>
          <table className="grid">
            <thead><tr><th>Stage</th><th>Status</th><th>ms</th><th>Detail</th></tr></thead>
            <tbody>
              {doc.history.map((h, n) => (
                <tr key={n}><td>{h.stage}</td><td>{h.status}</td><td>{h.duration_ms ?? ""}</td><td><small>{h.detail}</small></td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}
