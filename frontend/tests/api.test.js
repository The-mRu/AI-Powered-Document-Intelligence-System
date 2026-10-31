import { beforeEach, describe, expect, it, vi } from "vitest";

describe("API base URL configuration", () => {
  beforeEach(() => {
    vi.resetModules();
    sessionStorage.clear();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ documents: [] }),
    });
  });

  it("uses the same-origin local default", async () => {
    const { API_BASE, api } = await import("../src/api");

    await api.list();

    expect(API_BASE).toBe("");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/documents", expect.any(Object));
  });

  it("sends the owner key only after it is configured", async () => {
    const { api, setApiKey, clearApiKey } = await import("../src/api");

    await api.list();
    expect(globalThis.fetch.mock.calls[0][1].headers).not.toHaveProperty("X-API-Key");

    setApiKey("owner-secret");
    await api.upload([]);
    expect(globalThis.fetch.mock.calls[1][1].headers["X-API-Key"]).toBe("owner-secret");

    clearApiKey();
    expect(sessionStorage.getItem("apiKey")).toBeNull();
  });

  it("returns a clear message for unauthorized owner actions", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ detail: "Invalid or missing API key" }),
    });
    const { api } = await import("../src/api");

    await expect(api.upload([])).rejects.toThrow(
      "Owner API key is missing or invalid. Enter a valid key to perform this action."
    );
  });
});
