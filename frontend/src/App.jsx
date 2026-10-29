import { useState } from "react";
import { getApiKey, setApiKey } from "./api";
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
        <h1>Document Intelligence</h1>
        <StatsBar refreshKey={tick} />
        <input
          className="apikey"
          type="password"
          placeholder="API key (only if enabled)"
          defaultValue={getApiKey()}
          onBlur={(e) => {
            setApiKey(e.target.value);
            refresh();
          }}
        />
      </header>
      <main>
        <div className="col">
          <Upload onUploaded={(docs) => { refresh(); const first = docs.find((d) => d.id); if (first) setSelectedId(first.id); }} />
          <DocumentList selectedId={selectedId} onSelect={setSelectedId} refreshKey={tick} />
          <Search onSelect={setSelectedId} />
        </div>
        <div className="col">
          {selectedId ? <DocumentDetail key={selectedId} id={selectedId} onChanged={refresh} /> : (
            <section className="card"><p className="muted">Upload a document or select one from the list to inspect it.</p></section>
          )}
        </div>
      </main>
    </div>
  );
}
