export type UserRole = "admin" | "technician" | "requester";

export type TicketStatus =
  | "aberto"
  | "em_atendimento"
  | "aguardando_usuario"
  | "resolvido"
  | "fechado";

export type TicketPriority = "baixa" | "media" | "alta" | "critica";
export type TicketCategory = "hardware" | "software" | "rede" | "acesso" | "outro";

export interface Ticket {
  id: number;
  title: string;
  description: string;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  requester_id: number | null;
  assigned_technician_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: number;
  full_name: string | null;
  email: string;
  role: UserRole;
  is_active: boolean;
}

export interface AccessToken {
  access_token: string;
  token_type: string;
}

export interface TicketFilters {
  period: "7" | "30" | "90" | "all";
  status: "all" | TicketStatus;
  priority: "all" | TicketPriority;
}
