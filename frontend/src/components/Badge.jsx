export default function Badge({ kind, children }) {
  return <span className={`badge ${kind}`}>{children ?? kind}</span>;
}
