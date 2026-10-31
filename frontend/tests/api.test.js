import { beforeEach, describe, expect, it, vi } from "vitest";

describe("API base URL configuration", () => {
  beforeEach(() => {
    vi.resetModules();
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

  it("does not send API-key headers", async () => {
    const { api } = await import("../src/api");
    await api.list();
    await api.upload([]);
    expect(globalThis.fetch.mock.calls[0][1].headers).not.toHaveProperty("X-API-Key");
    expect(globalThis.fetch.mock.calls[1][1].headers).not.toHaveProperty("X-API-Key");
  });
});
