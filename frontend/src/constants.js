export const FIELDS = [
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date (YYYY-MM-DD)"],
  ["supplier_name", "Supplier"],
  ["customer_name", "Customer"],
  ["subtotal", "Subtotal"],
  ["tax", "Tax"],
  ["discount", "Discount"],
  ["total", "Total"],
  ["currency", "Currency (e.g. USD)"],
];

export const ACTIVE = ["queued", "processing"];
export const READY = ["completed", "needs_review"];

const MESSAGES = {
  unsupported_extension: "File type not supported",
  unsupported_file: "File type not supported",
  file_too_large: "File is too large",
  empty_file: "File is empty",
  corrupted_file: "File is corrupted or unreadable",
  encrypted_file: "File is password protected",
  no_text_extracted: "No text could be read from this file",
  extraction_failed: "AI extraction failed (can be retried)",
  queue_unavailable: "Job queue unavailable (can be retried)",
  internal_error: "Unexpected processing error",
};
export const friendly = (code) => MESSAGES[code] || code || "";

export const fmtBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
export const fmtMoney = (v, cur) => (v === null || v === undefined ? "" : `${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${cur || ""}`.trim());
