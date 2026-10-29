import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api.js", () => ({
  api: { upload: vi.fn(), list: vi.fn(), detail: vi.fn(), result: vi.fn(), pages: vi.fn(), correct: vi.fn(),
         approve: vi.fn(), reprocess: vi.fn(), reprocessFailed: vi.fn(), search: vi.fn(), stats: vi.fn() },
  getApiKey: () => "",
  setApiKey: vi.fn(),
}));
import { api } from "../src/api.js";
import DocumentDetail from "../src/components/DocumentDetail.jsx";
import DocumentList from "../src/components/DocumentList.jsx";
import Highlight from "../src/components/Highlight.jsx";
import Search from "../src/components/Search.jsx";
import Upload from "../src/components/Upload.jsx";

const field = (value, status = "ok", flags = []) => ({ value, status, flags, confidence: 1, evidence: value ? `evidence ${value}` : null });
const RESULT = {
  document_id: "d1", status: "needs_review", corrections: null,
  effective: {
    invoice_number: field("INV-1"), invoice_date: field("2024-03-15"), supplier_name: field("Acme"), customer_name: field("Globex"),
    supplier_address: field("1 Main St"), supplier_city: field("Hyderabad"), supplier_postal_code: field("500054"),
    customer_address: field("2 Market St"), customer_city: field("Mumbai"), customer_postal_code: field("509321"),
    ship_to_name: field("Jarsh Complex"), ship_to_address: field("3 Delivery Rd"), ship_to_city: field("Mumbai"), ship_to_postal_code: field("509876"),
    subtotal: field("100.00"), tax: field("10.00"), discount: field(null, "missing"), total: field("110.00"), currency: field(null, "missing"),
    line_items: [{ description: "Widget", quantity: "2", unit: null, unit_price: "50.00", line_total: "100.00", flags: [] }],
  },
  validation: { issues: [
    { rule: "missing_recommended_field", severity: "warning", field: "currency", message: "Field 'currency' is missing" },
    { rule: "totals_consistent", severity: "info", field: "total", message: "Totals reconcile" } ] },
};
const DOC = { id: "d1", filename: "inv.pdf", status: "needs_review", kind: "pdf", attempts: 1, warnings: [], history: [],
              progress: { pages_done: 1, page_count: 1, percent: 100 } };

beforeEach(() => {
  vi.clearAllMocks();
  api.detail.mockResolvedValue(DOC);
  api.result.mockResolvedValue(RESULT);
  api.pages.mockResolvedValue({ items: [] });
  api.stats.mockResolvedValue({ total: 0, counts: {}, processing_seconds: {} });
});

describe("Upload", () => {
  it("sends every chosen file in one request", async () => {
    api.upload.mockResolvedValue({ documents: [{ id: "1", filename: "a.pdf", status: "queued" }, { filename: "x.exe", status: "rejected", error: "unsupported_extension" }] });
    render(<Upload onUploaded={() => {}} />);
    const files = [new File(["a"], "a.pdf"), new File(["b"], "x.exe")];
    fireEvent.change(screen.getByTestId("file-input"), { target: { files } });
    fireEvent.click(await screen.findByText("Upload 2 files"));
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(1));
    expect(api.upload.mock.calls[0][0]).toHaveLength(2);
    expect(await screen.findByText(/rejected – File type not supported/)).toBeInTheDocument();
  });
});

describe("Highlight (XSS safety)", () => {
  it("renders <mark> hits but never injects document text as HTML", () => {
    const { container } = render(<pre><Highlight text={'a <mark>hit</mark> <img src=x onerror=alert(1)>'} /></pre>);
    expect(container.querySelectorAll("mark")).toHaveLength(1);
    expect(container.querySelector("mark").textContent).toBe("hit");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("DocumentList", () => {
  it("shows a progress bar only for work in progress and a reason for failures", async () => {
    api.list.mockResolvedValue({ total: 3, items: [
      { id: "1", filename: "busy.pdf", status: "processing", progress: { percent: 40 } },
      { id: "2", filename: "bad.pdf", status: "failed", error_code: "corrupted_file", progress: {} },
      { id: "3", filename: "ok.pdf", status: "completed", progress: { percent: 100 }, supplier_name: "Acme", invoice_number: "INV-1", total: 110, currency: "USD" } ] });
    render(<DocumentList selectedId={null} onSelect={() => {}} refreshKey={0} />);
    expect(await screen.findByText("busy.pdf")).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByText("File is corrupted or unreadable")).toBeInTheDocument();
  });
});

describe("DocumentDetail", () => {
  it("shows validation problems first and extracted values", async () => {
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    expect(await screen.findByText("Field 'currency' is missing")).toBeInTheDocument();
    expect(screen.getByText("1 issue(s) need review")).toBeInTheDocument();
    expect(screen.getByText("INV-1")).toBeInTheDocument();
    expect(screen.getByText("Approve as is")).toBeInTheDocument();
  });

  it("renders every returned line item and payment fields", async () => {
    api.result.mockResolvedValue({
      ...RESULT,
      effective: {
        ...RESULT.effective,
        payments_received: field("20.00"),
        balance_due: field("90.00"),
        line_items: Array.from({ length: 6 }, (_, i) => ({
          description: `Milk ${i + 1}`, quantity: "2", unit: "litres",
          unit_price: "80", line_total: "160", tax: "10%", discount: "10%",
          evidence: "Milk 2 litres 80 160", flags: [],
        })),
      },
    });

    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    expect(await screen.findByText("Payments received")).toBeInTheDocument();
    expect(screen.getByText("20.00")).toBeInTheDocument();
    const lineTable = screen.getByText("Line items").nextElementSibling;
    expect(within(lineTable).getAllByRole("row")).toHaveLength(7);
    expect(screen.getAllByText(/quantity:/)).toHaveLength(6);
    expect(screen.getAllByText(/tax:/)).toHaveLength(6);
  });

  it("renders all invoice parties separately", async () => {
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    expect(await screen.findByText("Supplier / From")).toBeInTheDocument();
    expect(screen.getByText("Customer / Bill To")).toBeInTheDocument();
    expect(screen.getByText("Shipping Recipient / Ship To")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Jarsh Complex")).toBeInTheDocument();
  });

  it("sends only the changed fields when saving a correction", async () => {
    api.correct.mockResolvedValue({ ...RESULT, status: "completed" });
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    fireEvent.click(await screen.findByText("Edit values"));
    fireEvent.change(screen.getByLabelText("Currency (e.g. USD)"), { target: { value: "USD" } });
    fireEvent.click(screen.getByText("Save corrections"));
    await waitFor(() => expect(api.correct).toHaveBeenCalledTimes(1));
    expect(api.correct).toHaveBeenCalledWith("d1", { fields: { currency: "USD" }, note: null });
  });

  it("shows the server's validation message when a correction is rejected", async () => {
    api.correct.mockRejectedValue(new Error("'total' must be a plain decimal number (e.g. 1150.50)"));
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    fireEvent.click(await screen.findByText("Edit values"));
    fireEvent.change(screen.getByLabelText("Total"), { target: { value: "abc" } });
    fireEvent.click(screen.getByText("Save corrections"));
    expect(await screen.findByRole("alert")).toHaveTextContent("must be a plain decimal number");
  });

  it("refuses to save when nothing changed", async () => {
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    fireEvent.click(await screen.findByText("Edit values"));
    fireEvent.click(screen.getByText("Save corrections"));
    expect(await screen.findByRole("alert")).toHaveTextContent("No changes");
    expect(api.correct).not.toHaveBeenCalled();
  });

  it("offers to reprocess a failed document", async () => {
    api.detail.mockResolvedValue({ ...DOC, status: "failed", error_code: "extraction_failed", error_message: "LLM call failed" });
    api.reprocess.mockResolvedValue({});
    render(<DocumentDetail id="d1" onChanged={() => {}} />);
    expect(await screen.findByText("AI extraction failed (can be retried)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Reprocess"));
    await waitFor(() => expect(api.reprocess).toHaveBeenCalledWith("d1"));
  });
});

describe("Search", () => {
  it("passes the chosen mode and filters to the API", async () => {
    api.search.mockResolvedValue({ results: [{ document_id: "d1", filename: "inv.pdf", status: "completed", score: 0.5, snippet: "see <mark>Acme</mark>", supplier_name: "Acme", invoice_number: "INV-1", total: 110, currency: "USD" }] });
    render(<Search onSelect={() => {}} />);
    fireEvent.change(screen.getByLabelText("search query"), { target: { value: "acme" } });
    fireEvent.change(screen.getByLabelText("search mode"), { target: { value: "semantic" } });
    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => expect(api.search).toHaveBeenCalled());
    expect(api.search.mock.calls[0][0]).toMatchObject({ q: "acme", mode: "semantic" });
    expect(await screen.findByText("inv.pdf")).toBeInTheDocument();
  });
});
