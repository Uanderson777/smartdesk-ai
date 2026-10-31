export type Role = "requester" | "technician" | "admin";
export type Status =
  "aberto" | "em_atendimento" | "aguardando_usuario" | "resolvido" | "fechado";
export type User = {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
};
export type Ticket = {
  id: number;
  title: string;
  description: string;
  category: string;
  priority: string;
  status: Status;
  requester_id: number | null;
  assigned_technician_id: number | null;
  created_at: string;
  updated_at: string;
};
export type Session = {
  token: string;
  id: number;
  email: string;
  role: Role;
  expiresAt: number;
};
export const roles: Record<Role, string> = {
  requester: "Solicitante",
  technician: "Técnico",
  admin: "Administrador",
};
export const statuses: Record<Status, string> = {
  aberto: "Aberto",
  em_atendimento: "Em atendimento",
  aguardando_usuario: "Aguardando usuário",
  resolvido: "Resolvido",
  fechado: "Fechado",
};
export const priorities: Record<string, string> = {
  baixa: "Baixa",
  media: "Média",
  alta: "Alta",
  critica: "Crítica",
};
export const categories: Record<string, string> = {
  hardware: "Hardware",
  software: "Software",
  rede: "Rede",
  acesso: "Acesso",
  outro: "Outro",
};
