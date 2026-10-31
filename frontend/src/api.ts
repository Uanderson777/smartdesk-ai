import type { Role } from "./types";
// Only public routing configuration belongs in Vite variables.
const base = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(
  /\/$/,
  "",
);
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  token?: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method,
      signal,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "Não foi possível conectar à API. Tente novamente em instantes.",
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Confira os campos informados e tente novamente."
          : "Não foi possível concluir a solicitação.";
    throw new ApiError(
      response.status,
      response.status === 401 && token
        ? "Sua sessão expirou. Entre novamente."
        : message,
    );
  }
  if (
    data === null ||
    !response.headers.get("content-type")?.includes("application/json")
  )
    throw new ApiError(
      502,
      "A API retornou uma resposta inesperada. Verifique a conexão com o serviço.",
    );
  return data as T;
}
export async function detectRole(
  token: string,
  signal?: AbortSignal,
): Promise<Role> {
  try {
    await request("/users?limit=1", token, "GET", undefined, signal);
    return "admin";
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 403) throw error;
  }
  try {
    await request(
      "/tickets/available?limit=1",
      token,
      "GET",
      undefined,
      signal,
    );
    return "technician";
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 403) throw error;
  }
  // Confirm this is an authenticated requester, rather than treating every failure as a role.
  await request("/tickets?limit=1", token, "GET", undefined, signal);
  return "requester";
}
export function tokenIdentity(token: string) {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    if (
      !/^\d+$/.test(payload.sub) ||
      !Number.isSafeInteger(Number(payload.sub)) ||
      typeof payload.exp !== "number" ||
      !Number.isFinite(payload.exp) ||
      payload.exp * 1000 <= Date.now()
    )
      throw new Error();
    return { id: Number(payload.sub), expiresAt: payload.exp * 1000 };
  } catch {
    throw new ApiError(
      401,
      "Não foi possível iniciar a sessão. Entre novamente.",
    );
  }
}
