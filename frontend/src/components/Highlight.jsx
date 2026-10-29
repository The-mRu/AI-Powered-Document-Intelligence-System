// The server marks search hits with <mark>…</mark>. The rest of the snippet is document text,
// which must never be treated as HTML (XSS), so we split on the markers and let React escape the text.
export default function Highlight({ text }) {
  const parts = String(text ?? "").split(/(<mark>|<\/mark>)/);
  let on = false;
  const out = [];
  parts.forEach((p, i) => {
    if (p === "<mark>") on = true;
    else if (p === "</mark>") on = false;
    else if (p) out.push(on ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>);
  });
  return <>{out}</>;
}
