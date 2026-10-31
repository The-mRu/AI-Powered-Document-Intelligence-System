import { useState } from "react";
import DocumentDetail from "./components/DocumentDetail";
import DocumentList from "./components/DocumentList";
import Search from "./components/Search";
import StatsBar from "./components/StatsBar";
import Upload from "./components/Upload";

export default function App() {
  const [selectedId, setSelectedId] = useState(null);
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((t) => t + 1);

  return (
    <div className="app">
      <header>
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">D</div>
          <div>
            <h1>DocIntel</h1>
            <p>Document intelligence workspace</p>
          </div>
        </div>
        <StatsBar refreshKey={tick} />
      </header>
      <main>
        <div className="col">
          <Upload onUploaded={(docs) => { refresh(); const first = docs.find((d) => d.id); if (first) setSelectedId(first.id); }} />
          <DocumentList selectedId={selectedId} onSelect={setSelectedId} refreshKey={tick} />
          <Search onSelect={setSelectedId} />
        </div>
        <div className="col">
          {selectedId ? <DocumentDetail key={selectedId} id={selectedId} onChanged={refresh}
            onDeleted={() => { setSelectedId(null); refresh(); }} /> : (
            <section className="card empty-state">
              <div className="empty-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M7 3.75h7.25L19 8.5v11.75H7z" />
                  <path d="M14 3.75V9h5M10 13h6M10 16h4" />
                </svg>
              </div>
              <h2>No document selected</h2>
              <p>Upload a document or select one from your document list to view its details.</p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
