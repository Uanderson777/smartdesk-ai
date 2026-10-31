import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, detectRole, request, tokenIdentity } from "../src/api";
function reply(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
afterEach(() => vi.unstubAllGlobals());
describe("existing API contract", () => {
  it("uses JSON POST and authorization only on protected requests", async () => {
    const fetcher = vi.fn().mockResolvedValue(reply({ id: 2 }));
    vi.stubGlobal("fetch", fetcher);
    await request("/tickets", "synthetic-fixture", "POST", { title: "Teste" });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tickets",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer synthetic-fixture",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ title: "Teste" }),
      }),
    );
  });
  it.each([
    ["admin", [200]],
    ["technician", [403, 200]],
    ["requester", [403, 403, 200]],
  ] as const)(
    "identifies %s only through existing protected routes",
    async (role, codes) => {
      const fetcher = vi.fn();
      for (const status of codes)
        fetcher.mockResolvedValueOnce(
          reply(status === 200 ? [] : { detail: "Sem permissão" }, status),
        );
      vi.stubGlobal("fetch", fetcher);
      expect(await detectRole("synthetic-fixture")).toBe(role);
      expect(fetcher).toHaveBeenCalledTimes(codes.length);
    },
  );
  it("does not interpret server outages as requester permission", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(reply({ detail: "Indisponível" }, 503));
    vi.stubGlobal("fetch", fetcher);
    await expect(detectRole("synthetic-fixture")).rejects.toMatchObject({
      status: 503,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects HTML returned by an incorrectly configured proxy", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html/>", { headers: { "Content-Type": "text/html" } }),
        ),
    );
    await expect(request("/tickets")).rejects.toMatchObject({ status: 502 });
  });
  it("returns a readable network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(request("/tickets")).rejects.toMatchObject({ status: 0 });
  });
  it("does not show validation inputs containing credentials in errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          reply({ detail: [{ input: "private-input" }] }, 422),
        ),
    );
    try {
      await request("/auth/login");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as Error).message).not.toContain("private-input");
    }
  });
  it("rejects expired and malformed session metadata", () => {
    expect(() => tokenIdentity("invalid")).toThrow();
    const fixture = `fixture.${btoa(JSON.stringify({ sub: "7", exp: 1 }))}.fixture`;
    expect(() => tokenIdentity(fixture)).toThrow();
  });
  it("reads session metadata without treating it as server authorization", () => {
    const exp = Math.floor(Date.now() / 1000) + 1800;
    const fixture = `fixture.${btoa(JSON.stringify({ sub: "7", exp }))}.fixture`;
    expect(tokenIdentity(fixture)).toEqual({ id: 7, expiresAt: exp * 1000 });
  });
});
