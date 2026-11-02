import axios, { AxiosHeaders, type Method } from "axios";
import type {
  AccessToken,
  Ticket,
  TicketCategory,
  TicketPriority,
  TicketStatus,
  TicketTriageResponse,
  TenantOption,
  User,
  UserRole,
} from "./types";

export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL?.trim() ||
  (import.meta.env.DEV ? "" : "https://smartdesk-ai-0rev.onrender.com")
).replace(/\/+$/, "");
const API_REQUEST_TIMEOUT_MS = 60_000;

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: API_REQUEST_TIMEOUT_MS,
  transitional: { clarifyTimeoutError: true },
  headers: { "Content-Type": "application/json" },
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (!axios.isAxiosError(error)) return Promise.reject(error);

    const response = error.response;
    if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
      return Promise.reject(
        new ApiError(
          "A API demorou para responder. Ela pode estar iniciando; tente novamente em instantes.",
          0,
        ),
      );
    }

    if (!response) {
      return Promise.reject(
        new ApiError(
          `Não foi possível conectar à API em ${API_BASE}. Verifique se o serviço está disponível e se o CORS permite este site.`,
          0,
        ),
      );
    }

    let message = `A API retornou erro ${response.status}.`;
    const detail = response.data?.detail as
      | string
      | Array<{ msg?: string }>
      | { message?: string; companies?: TenantOption[] }
      | undefined;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((item) => item.msg ?? "Dados inválidos.").join(" ");
    } else if (detail && typeof detail.message === "string") {
      message = detail.message;
    }

    return Promise.reject(new ApiError(message, response.status, detail));
  },
);

async function request<T>(
  path: string,
  token?: string,
  init: { method?: Method; body?: string } = {},
): Promise<T> {
  const headers = new AxiosHeaders();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await apiClient.request<T>({
    url: path,
    method: init.method,
    data: init.body,
    headers,
  });
  return response.data;
}

export const api = {
  login: (email: string, password: string, companyId?: number) =>
    request<AccessToken>("/api/v1/auth/login", undefined, {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        ...(companyId === undefined ? {} : { company_id: companyId }),
      }),
    }),

  currentUser: (token: string) =>
    request<User>("/api/v1/auth/me", token),

  register: (fullName: string, email: string, password: string) =>
    request<User>("/api/v1/auth/register", undefined, {
      method: "POST",
      body: JSON.stringify({ full_name: fullName, email, password }),
    }),

  async identifyRole(token: string): Promise<UserRole> {
    try {
      await request<User[]>("/api/v1/users?limit=1", token);
      return "admin";
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 403) throw error;
    }
    try {
      await request<Ticket[]>("/api/v1/tickets/available?limit=1", token);
      return "technician";
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 403) throw error;
    }
    return "requester";
  },

  async listTickets(token: string): Promise<Ticket[]> {
    const tickets: Ticket[] = [];
    const pageSize = 100;
    for (let skip = 0; ; skip += pageSize) {
      const page = await request<Ticket[]>(
        `/api/v1/tickets?skip=${skip}&limit=${pageSize}`,
        token,
      );
      tickets.push(...page);
      if (page.length < pageSize) return tickets;
    }
  },

  async listAvailableTickets(token: string): Promise<Ticket[]> {
    const tickets: Ticket[] = [];
    const pageSize = 100;
    for (let skip = 0; ; skip += pageSize) {
      const page = await request<Ticket[]>(
        `/api/v1/tickets/available?skip=${skip}&limit=${pageSize}`,
        token,
      );
      tickets.push(...page);
      if (page.length < pageSize) return tickets;
    }
  },

  async listUsers(token: string): Promise<User[]> {
    const users: User[] = [];
    const pageSize = 100;
    for (let skip = 0; ; skip += pageSize) {
      const page = await request<User[]>(
        `/api/v1/users?skip=${skip}&limit=${pageSize}`,
        token,
      );
      users.push(...page);
      if (page.length < pageSize) return users;
    }
  },

  createTicket: (
    token: string,
    input: {
      title: string;
      description: string;
      category: TicketCategory;
      priority: TicketPriority;
    },
  ) =>
    request<Ticket>("/api/v1/tickets", token, {
      method: "POST",
      body: JSON.stringify(input),
    }),

  triageTicket: (token: string, ticketId: number) =>
    request<TicketTriageResponse>(
      `/api/v1/tickets/${ticketId}/triage`,
      token,
      { method: "POST" },
    ),

  claimTicket: (token: string, ticketId: number) =>
    request<Ticket>(`/api/v1/tickets/${ticketId}/claim`, token, {
      method: "POST",
    }),

  assignTicket: (token: string, ticketId: number, technicianId: number | null) =>
    request<Ticket>(`/api/v1/tickets/${ticketId}/assignee`, token, {
      method: "PATCH",
      body: JSON.stringify({ technician_id: technicianId }),
    }),

  updateStatus: (token: string, ticketId: number, status: TicketStatus) =>
    request<Ticket>(`/api/v1/tickets/${ticketId}/status`, token, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  updateUserRole: (token: string, userId: number, role: UserRole) =>
    request<User>(`/api/v1/users/${userId}/role`, token, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),

  updateUserActive: (token: string, userId: number, isActive: boolean) =>
    request<User>(`/api/v1/users/${userId}/active`, token, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),
};
