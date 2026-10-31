import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { ApiError, detectRole, request, tokenIdentity } from "../src/api";
import type { Role, Ticket, User } from "../src/types";
vi.mock("../src/api", async (original) => ({
  ...(await original<typeof import("../src/api")>()),
  request: vi.fn(),
  detectRole: vi.fn(),
  tokenIdentity: vi.fn(),
}));
const call = vi.mocked(request),
  roleCall = vi.mocked(detectRole);
const ticket: Ticket = {
  id: 17,
  title: "Computador sem acesso à rede",
  description: "Conexão indisponível desde o início do expediente.",
  category: "rede",
  priority: "alta",
  status: "aberto",
  requester_id: 2,
  assigned_technician_id: null,
  created_at: "2026-10-31T10:00:00Z",
  updated_at: "2026-10-31T10:00:00Z",
};
let profile: Role;
let rows: Ticket[];
let people: User[];
beforeEach(() => {
  vi.resetAllMocks();
  profile = "requester";
  rows = [{ ...ticket }];
  people = [
    {
      id: 7,
      email: "tecnico@example.test",
      role: "technician",
      is_active: true,
    },
  ];
  roleCall.mockImplementation(async () => profile);
  vi.mocked(tokenIdentity).mockReturnValue({
    id: 7,
    expiresAt: Date.now() + 1800000,
  });
  call.mockImplementation(async (path, _token, method = "GET", data) => {
    if (path === "/auth/login") return { access_token: "synthetic-fixture" };
    if (path === "/auth/register")
      return { id: 2, email: "pessoa@example.test" };
    if (path.startsWith("/users?")) return people;
    if (path.includes("/role")) {
      people = people.map((person) => ({
        ...person,
        role: (data as User).role,
      }));
      return people[0];
    }
    if (path.includes("/active")) {
      people = people.map((person) => ({ ...person, is_active: false }));
      return people[0];
    }
    if (path.includes("/claim"))
      return { ...ticket, assigned_technician_id: 7, status: "em_atendimento" };
    if (path.includes("/status"))
      return { ...ticket, assigned_technician_id: 7, ...(data as object) };
    if (path.includes("/assignee")) return { ...ticket, ...(data as object) };
    if (path === "/tickets" && method === "POST") {
      rows = [{ ...ticket, ...(data as object) }];
      return rows[0];
    }
    if (path.startsWith("/tickets?") || path.startsWith("/tickets/available?"))
      return rows;
    if (path === "/tickets/17") return rows[0];
    throw new Error("Unexpected API request in test");
  });
});
async function login(as: Role = "requester") {
  profile = as;
  render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("E-mail"), "pessoa@example.test");
  await user.type(screen.getByLabelText("Senha"), "fixture-only-password");
  await user.click(screen.getByRole("button", { name: /Entrar na central/ }));
  await screen.findByRole("heading", { name: /Visão geral/ });
  await waitFor(() =>
    expect(
      screen.queryByLabelText("Carregando registros"),
    ).not.toBeInTheDocument(),
  );
  return user;
}
describe("authentication and requester flows", () => {
  it("registers using existing endpoint and returns to login without automatic sign-in", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Criar uma conta" }));
    await user.type(screen.getByLabelText("E-mail"), "pessoa@example.test");
    await user.type(screen.getByLabelText("Senha"), "fixture-only-password");
    await user.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(
      await screen.findByText("Conta criada. Entre com seu e-mail e senha."),
    ).toBeInTheDocument();
    expect(call).toHaveBeenCalledWith(
      "/auth/register",
      undefined,
      "POST",
      expect.objectContaining({ email: "pessoa@example.test" }),
    );
    expect(roleCall).not.toHaveBeenCalled();
  });
  it("shows login failure without opening protected screens", async () => {
    call.mockRejectedValueOnce(new ApiError(401, "E-mail ou senha inválidos."));
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("E-mail"), "pessoa@example.test");
    await user.type(screen.getByLabelText("Senha"), "fixture-only-password");
    await user.click(screen.getByRole("button", { name: /Entrar na central/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "E-mail ou senha inválidos.",
    );
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
  it("shows only requester actions and ticket details", async () => {
    const user = await login();
    expect(
      screen.queryByRole("button", { name: "Usuários" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Fila do técnico" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir chamado 17" }));
    expect(
      await screen.findByRole("region", { name: "Detalhes do chamado" }),
    ).toHaveTextContent(ticket.description);
    expect(
      screen.queryByRole("button", { name: "Salvar status" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Assumir chamado" }),
    ).not.toBeInTheDocument();
  });
  it("creates a ticket with the backend category and priority values", async () => {
    const user = await login();
    await user.click(screen.getByRole("button", { name: "Novo chamado" }));
    await user.type(screen.getByLabelText("Título"), "Impressora indisponível");
    await user.type(
      screen.getByLabelText("Descrição"),
      "Impressora não responde às solicitações de impressão.",
    );
    await user.selectOptions(screen.getByLabelText("Categoria"), "hardware");
    await user.selectOptions(screen.getByLabelText("Prioridade"), "critica");
    await user.click(screen.getByRole("button", { name: "Enviar chamado" }));
    expect(
      await screen.findByText("Chamado aberto com sucesso."),
    ).toBeInTheDocument();
    expect(call).toHaveBeenCalledWith(
      "/tickets",
      "synthetic-fixture",
      "POST",
      expect.objectContaining({ category: "hardware", priority: "critica" }),
    );
  });
  it("filters records and shows an empty search state", async () => {
    const user = await login();
    await user.type(
      screen.getByLabelText("Buscar chamados nesta página"),
      "inexistente",
    );
    expect(screen.getByText("Nenhum resultado por aqui.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Buscar chamados nesta página"));
    await user.selectOptions(
      screen.getByLabelText("Filtrar status"),
      "resolvido",
    );
    expect(
      screen.queryByRole("button", { name: "Abrir chamado 17" }),
    ).not.toBeInTheDocument();
  });
  it("logs out and does not persist session in browser storage", async () => {
    const user = await login();
    await user.click(screen.getByRole("button", { name: "Sair" }));
    expect(
      await screen.findByRole("button", { name: /Entrar na central/ }),
    ).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
  it("clears the session when a protected request returns 401", async () => {
    const user = await login();
    call.mockRejectedValueOnce(
      new ApiError(401, "Sua sessão expirou. Entre novamente."),
    );
    await user.click(screen.getByRole("button", { name: "Abrir chamado 17" }));
    expect(
      await screen.findByText("Sua sessão expirou. Entre novamente."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
describe("technician and administrator flows", () => {
  it("allows a technician to claim an available ticket then update its status", async () => {
    const user = await login("technician");
    expect(
      screen.queryByRole("button", { name: "Novo chamado" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fila do técnico" }));
    await screen.findByRole("heading", { name: /Fila de atendimento/ });
    await user.click(
      await screen.findByRole("button", { name: "Abrir chamado 17" }),
    );
    expect(
      screen.queryByRole("button", { name: "Salvar status" }),
    ).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole("button", { name: "Assumir chamado" }),
    );
    expect(
      await screen.findByText("Chamado atribuído a você."),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "resolvido");
    await user.click(screen.getByRole("button", { name: "Salvar status" }));
    expect(await screen.findByText("Status atualizado.")).toBeInTheDocument();
    expect(call).toHaveBeenCalledWith(
      "/tickets/17/status",
      "synthetic-fixture",
      "PATCH",
      { status: "resolvido" },
    );
  });
  it("shows a claim conflict instead of claiming success", async () => {
    const user = await login("technician");
    await user.click(screen.getByRole("button", { name: "Abrir chamado 17" }));
    await screen.findByRole("button", { name: "Assumir chamado" });
    call.mockRejectedValueOnce(new ApiError(409, "Chamado já está atribuído."));
    await user.click(screen.getByRole("button", { name: "Assumir chamado" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Chamado já está atribuído.",
    );
    expect(
      screen.queryByText("Chamado atribuído a você."),
    ).not.toBeInTheDocument();
  });
  it("lets an administrator update user role and activation", async () => {
    const user = await login("admin");
    await user.click(screen.getByRole("button", { name: "Usuários" }));
    await user.selectOptions(
      await screen.findByLabelText("Perfil de tecnico@example.test"),
      "requester",
    );
    await screen.findByText("Perfil atualizado.");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Desativar" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "Desativar" }));
    expect(await screen.findByText("Acesso atualizado.")).toBeInTheDocument();
    expect(call).toHaveBeenCalledWith(
      "/users/7/active",
      "synthetic-fixture",
      "PATCH",
      { is_active: false },
    );
  });
  it("keeps last administrator protection errors visible", async () => {
    const user = await login("admin");
    await user.click(screen.getByRole("button", { name: "Usuários" }));
    await screen.findByRole("button", { name: "Desativar" });
    call.mockRejectedValueOnce(
      new ApiError(
        409,
        "Não é possível desativar o último administrador ativo.",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Desativar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "último administrador ativo",
    );
  });
  it("assigns a technician and supports removing an assignment", async () => {
    const user = await login("admin");
    await user.click(screen.getByRole("button", { name: "Abrir chamado 17" }));
    const field = await screen.findByLabelText("Número do técnico");
    await user.type(field, "7");
    await user.click(screen.getByRole("button", { name: "Salvar atribuição" }));
    await screen.findByText("Atribuição atualizada.");
    await user.clear(screen.getByLabelText("Número do técnico"));
    await user.click(screen.getByRole("button", { name: "Salvar atribuição" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        "/tickets/17/assignee",
        "synthetic-fixture",
        "PATCH",
        { technician_id: null },
      ),
    );
  });
  it("does not offer assignment for historical tickets without requester", async () => {
    rows = [{ ...ticket, requester_id: null }];
    const user = await login("admin");
    await user.click(screen.getByRole("button", { name: "Abrir chamado 17" }));
    expect(await screen.findByText("Registro histórico")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Número do técnico"),
    ).not.toBeInTheDocument();
  });
  it("rechecks permissions after a profile change", async () => {
    const user = await login("admin");
    profile = "requester";
    await user.click(screen.getByRole("button", { name: "Usuários" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Usuários" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByRole("heading", { name: /Visão geral/ }),
    ).toBeInTheDocument();
  });
  it("loads the next server page when the current page is full", async () => {
    rows = Array.from({ length: 20 }, (_, i) => ({ ...ticket, id: i + 1 }));
    const user = await login();
    await user.click(screen.getByRole("button", { name: "Próxima página" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        "/tickets?skip=20&limit=20",
        "synthetic-fixture",
        "GET",
        undefined,
        expect.any(AbortSignal),
      ),
    );
  });
});
