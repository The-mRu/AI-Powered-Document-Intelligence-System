export const PARTY_FIELDS = {
  supplier: [["supplier_name", "Name"], ["supplier_address", "Address"], ["supplier_city", "City"], ["supplier_postal_code", "Postal code"]],
  customer: [["customer_name", "Name"], ["customer_address", "Address"], ["customer_city", "City"], ["customer_postal_code", "Postal code"]],
  shipping: [["ship_to_name", "Name"], ["ship_to_address", "Address"], ["ship_to_city", "City"], ["ship_to_postal_code", "Postal code"]],
};

export const GENERAL_FIELDS = [
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date (YYYY-MM-DD)"],
  ["subtotal", "Subtotal"],
  ["tax", "Tax"],
  ["discount", "Discount"],
  ["shipping", "Shipping"],
  ["other_charges", "Other charges"],
  ["total", "Total"],
  ["currency", "Currency (e.g. USD)"],
  ["payments_received", "Payments received"],
  ["balance_due", "Balance due"],
];
export const FIELDS = [...GENERAL_FIELDS, ...Object.values(PARTY_FIELDS).flat()];

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
