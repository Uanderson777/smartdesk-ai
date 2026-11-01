import type {
  AccessToken,
  Ticket,
  TicketCategory,
  TicketPriority,
  TicketStatus,
  User,
  UserRole,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new ApiError(
      "Não foi possível conectar à API. Verifique se o backend está em execução.",
      0,
    );
  }

  if (!response.ok) {
    let detail = `A API retornou erro ${response.status}.`;
    try {
      const body: { detail?: string | Array<{ msg?: string }> } =
        await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail.map((item) => item.msg ?? "Dados inválidos.").join(" ");
      }
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<AccessToken>("/api/v1/auth/login", undefined, {
      method: "POST",
      body: JSON.stringify({ email, password }),
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
