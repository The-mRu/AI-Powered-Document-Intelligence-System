import { useRef, useState } from "react";
import { api } from "../api";
import { fmtBytes, friendly } from "../constants";

const BATCH = 20; // the API accepts at most 20 files per request

export default function Upload({ onUploaded }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const input = useRef(null);

  const add = (list) => setFiles((prev) => [...prev, ...Array.from(list)]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const all = [];
      for (let i = 0; i < files.length; i += BATCH) {
        const res = await api.upload(files.slice(i, i + BATCH));
        all.push(...res.documents);
      }
      setResults(all);
      setFiles([]);
      onUploaded?.(all);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Upload documents</h2>
      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          add(e.dataTransfer.files);
        }}
        onClick={() => input.current?.click()}
      >
        Drop files here or click to choose
        <small>PDF, JPG, PNG, TIFF, XLSX, XLS, CSV</small>
        <input
          ref={input}
          data-testid="file-input"
          type="file"
          multiple
          hidden
          accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {files.length > 0 && (
        <>
          <ul className="filelist">
            {files.map((f, i) => (
              <li key={i}>
                {f.name} <small>{fmtBytes(f.size)}</small>
              </li>
            ))}
          </ul>
          <div className="row">
            <button onClick={submit} disabled={busy}>
              {busy ? "Uploading…" : `Upload ${files.length} file${files.length > 1 ? "s" : ""}`}
            </button>
            <button className="ghost" onClick={() => setFiles([])} disabled={busy}>
              Clear
            </button>
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
      {results && (
        <ul className="filelist">
          {results.map((r, i) => (
            <li key={i} className={r.status === "rejected" || r.error ? "error" : ""}>
              {r.filename}: {r.status === "rejected" ? `rejected – ${friendly(r.error)}` : r.error ? friendly(r.error) : "queued"}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
