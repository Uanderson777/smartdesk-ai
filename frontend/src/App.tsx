import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Headphones,
  LayoutDashboard,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { ApiError, detectRole, request, tokenIdentity } from "./api";
import {
  categories,
  priorities,
  roles,
  statuses,
  type Session,
  type Status,
  type Ticket,
  type User,
} from "./types";
const body = (form: HTMLFormElement) => Object.fromEntries(new FormData(form));
const date = (value: string) => new Date(value).toLocaleDateString("pt-BR");
function Brand() {
  return (
    <div className="brand">
      <span>
        <Headphones size={23} />
      </span>
      smartdesk<small>AI</small>
    </div>
  );
}
function ErrorNotice({ message }: { message: string }) {
  return message ? (
    <div className="notice error" role="alert">
      {message}
    </div>
  ) : null;
}
function Badge({ status }: { status: Status }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {statuses[status]}
    </span>
  );
}
function Auth({
  onLogin,
  notice,
}: {
  onLogin: (value: Session) => void;
  notice: string;
}) {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget,
      payload = body(form);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      if (register) {
        await request("/auth/register", undefined, "POST", payload);
        setRegister(false);
        setSuccess("Conta criada. Entre com seu e-mail e senha.");
        form.reset();
      } else {
        const data = await request<{ access_token: string }>(
          "/auth/login",
          undefined,
          "POST",
          payload,
        );
        const identity = tokenIdentity(data.access_token);
        const role = await detectRole(data.access_token);
        form.reset();
        onLogin({
          token: data.access_token,
          email: String(payload.email),
          role,
          ...identity,
        });
      }
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Não foi possível entrar.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="story-copy">
          <span className="eyebrow">SUA CENTRAL DE ATENDIMENTO</span>
          <h1>
            Menos obstáculos. <br />
            <em>Mais soluções.</em>
          </h1>
          <p>
            Um lugar para conectar pessoas, organizar chamados e fazer o
            trabalho seguir em frente.
          </p>
          <div className="story-line">
            <span>
              <ClipboardList size={19} /> Acompanhe cada chamado
            </span>
            <span>
              <ShieldCheck size={19} /> Acesso conforme seu perfil
            </span>
          </div>
        </div>
        <div className="story-footer">
          SmartDesk AI <span>Atendimento que aproxima.</span>
        </div>
      </section>
      <main className="auth-main">
        <div className="auth-card">
          <span className="eyebrow">BEM-VINDO AO SMARTDESK</span>
          <h2>{register ? "Seu primeiro passo." : "Bom ter você por aqui."}</h2>
          <p className="muted">
            {register
              ? "Crie sua conta de solicitante para começar."
              : "Entre para acompanhar o que precisa de atenção."}
          </p>
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          <ErrorNotice message={error} />
          {success && (
            <div className="notice success" role="status">
              {success}
            </div>
          )}
          <form onSubmit={submit}>
            <label>
              E-mail
              <input
                name="email"
                type="email"
                placeholder="voce@empresa.com"
                autoComplete="email"
                required
                maxLength={320}
              />
            </label>
            <label>
              Senha
              <input
                name="password"
                type="password"
                placeholder={register ? "No mínimo 8 caracteres" : "Sua senha"}
                autoComplete={register ? "new-password" : "current-password"}
                required
                minLength={register ? 8 : 1}
                maxLength={128}
              />
            </label>
            <button className="primary full" disabled={busy}>
              {busy
                ? "Aguarde…"
                : register
                  ? "Criar conta"
                  : "Entrar na central"}
              <ArrowUpRight size={18} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Já tem uma conta?" : "Primeiro acesso?"}{" "}
            <button
              className="link"
              disabled={busy}
              onClick={() => {
                setRegister(!register);
                setError("");
                setSuccess("");
              }}
            >
              {register ? "Entrar" : "Criar uma conta"}
            </button>
          </p>
          <div className="secure">
            <ShieldCheck size={15} /> Seus dados são protegidos pela
            autenticação do serviço.
          </div>
        </div>
      </main>
    </div>
  );
}
export default function App() {
  const [session, setSession] = useState<Session | null>(null),
    [notice, setNotice] = useState("");
  function logout(message = "") {
    setSession(null);
    setNotice(message);
  }
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(
      () => logout("Sua sessão expirou. Entre novamente."),
      Math.max(0, session.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [session]);
  return session ? (
    <Workspace key={session.id} session={session} onLogout={logout} />
  ) : (
    <Auth
      notice={notice}
      onLogin={(value) => {
        setNotice("");
        setSession(value);
      }}
    />
  );
}
type Page = "dashboard" | "tickets" | "available" | "users";
function Workspace({
  session,
  onLogout,
}: {
  session: Session;
  onLogout: (message?: string) => void;
}) {
  const [page, setPage] = useState<Page>("dashboard"),
    [role, setRole] = useState(session.role);
  const [tickets, setTickets] = useState<Ticket[]>([]),
    [users, setUsers] = useState<User[]>([]),
    [selected, setSelected] = useState<Ticket | null>(null);
  const [creating, setCreating] = useState(false),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0),
    [reload, setReload] = useState(0);
  const limit = 20;
  function fail(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      onLogout(error.message);
      return;
    }
    setError(
      error instanceof Error
        ? error.message
        : "Não foi possível concluir a solicitação.",
    );
  }
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      setSelected(null);
      setTickets([]);
      setUsers([]);
      try {
        const currentRole = await detectRole(session.token, controller.signal);
        if (controller.signal.aborted) return;
        setRole(currentRole);
        if (
          (page === "users" && currentRole !== "admin") ||
          (page === "available" && currentRole === "requester")
        ) {
          setPage("dashboard");
          setOffset(0);
          return;
        }
        const path =
          page === "users"
            ? "/users"
            : page === "available"
              ? "/tickets/available"
              : "/tickets";
        const data = await request<Ticket[] | User[]>(
          `${path}?skip=${offset}&limit=${limit}`,
          session.token,
          "GET",
          undefined,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          if (page === "users") setUsers(data as User[]);
          else setTickets(data as Ticket[]);
        }
      } catch (error) {
        if (!controller.signal.aborted) fail(error);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [page, offset, reload, session.token]);
  function navigate(next: Page) {
    setPage(next);
    setOffset(0);
    setQuery("");
    setFilter("");
    setMessage("");
    setError("");
    setCreating(false);
    setSelected(null);
  }
  async function action(
    operation: () => Promise<unknown>,
    success: string,
    refresh = false,
  ) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await operation();
      if (refresh) {
        setReload((value) => value + 1);
        setCreating(false);
      } else if (result && typeof result === "object" && "title" in result) {
        const updated = result as Ticket;
        setSelected(updated);
        setTickets((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
      }
      setMessage(success);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  async function open(ticket: Ticket) {
    setBusy(true);
    setError("");
    try {
      setSelected(
        await request<Ticket>(`/tickets/${ticket.id}`, session.token),
      );
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  const visible = tickets.filter(
    (item) =>
      (!filter || item.status === filter) &&
      `${item.title} ${item.id} ${item.category}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const userResults = users.filter((user) =>
    `${user.email} ${user.id}`.toLowerCase().includes(query.toLowerCase()),
  );
  const total = page === "users" ? users.length : tickets.length;
  const title = creating
    ? "Abrir um chamado"
    : page === "users"
      ? "Pessoas e permissões"
      : page === "available"
        ? "Fila de atendimento"
        : page === "tickets"
          ? role === "requester"
            ? "Meus chamados"
            : "Todos os chamados"
          : "Visão geral";
  return (
    <div className="workspace">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-label">CENTRAL DE ATENDIMENTO</div>
        <nav aria-label="Navegação principal">
          <button
            disabled={busy}
            className={page === "dashboard" ? "active" : ""}
            onClick={() => navigate("dashboard")}
          >
            <LayoutDashboard size={19} />
            Visão geral
          </button>
          <button
            disabled={busy}
            className={page === "tickets" ? "active" : ""}
            onClick={() => navigate("tickets")}
          >
            <ClipboardList size={19} />
            {role === "requester" ? "Meus chamados" : "Chamados"}
          </button>
          {role !== "requester" && (
            <button
              disabled={busy}
              className={page === "available" ? "active" : ""}
              onClick={() => navigate("available")}
            >
              <Headphones size={19} />
              Fila do técnico
            </button>
          )}
          {role === "admin" && (
            <button
              disabled={busy}
              className={page === "users" ? "active" : ""}
              onClick={() => navigate("users")}
            >
              <Users size={19} />
              Usuários
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-box">
            <ShieldCheck size={21} />
            <strong>Cada detalhe ajuda.</strong>
            <p>Descreva o problema com clareza para facilitar o atendimento.</p>
          </div>
          <div className="identity">
            <span className="avatar">
              {session.email.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong title={session.email}>{session.email}</strong>
              <small>{roles[role]}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sair"
              onClick={() => onLogout()}
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <div>
            Workspace <span>/</span> <strong>{roles[role]}</strong>
          </div>
          <span className="workspace-tag">
            <i />
            Central de suporte
          </span>
        </header>
        <main className="content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {page === "users" ? "ADMINISTRAÇÃO" : "SEU TRABALHO, EM ORDEM"}
              </span>
              <h1>
                {title}
                <span className="title-dot" aria-hidden="true">
                  .
                </span>
              </h1>
              <p className="muted">
                {creating
                  ? "Conte o que aconteceu. Nossa equipe acompanha com você."
                  : page === "users"
                    ? "Gerencie o acesso de quem faz parte da central."
                    : page === "available"
                      ? "Assuma um chamado e ajude a resolver o próximo problema."
                      : "Acompanhe solicitações e mantenha o atendimento em movimento."}
              </p>
            </div>
            {role !== "technician" && !creating && page !== "users" && (
              <button
                className="primary"
                disabled={loading}
                onClick={() => {
                  setCreating(true);
                  setSelected(null);
                  setError("");
                  setMessage("");
                }}
              >
                <Plus size={18} />
                Novo chamado
              </button>
            )}
          </div>
          <ErrorNotice message={error} />
          {message && (
            <div className="notice success" role="status">
              <Check size={17} />
              {message}
            </div>
          )}
          {creating ? (
            <section className="panel create-panel">
              <div className="section-heading">
                <h2>O que precisa de atenção?</h2>
                <button
                  className="icon-button"
                  aria-label="Cancelar novo chamado"
                  disabled={busy}
                  onClick={() => setCreating(false)}
                >
                  <X size={20} />
                </button>
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const payload = body(event.currentTarget);
                  void action(
                    () => request("/tickets", session.token, "POST", payload),
                    "Chamado aberto com sucesso.",
                    true,
                  );
                }}
              >
                <label>
                  Título
                  <input
                    name="title"
                    required
                    minLength={5}
                    maxLength={160}
                    placeholder="Resuma o problema em poucas palavras"
                  />
                </label>
                <label>
                  Descrição
                  <textarea
                    name="description"
                    required
                    minLength={10}
                    maxLength={5000}
                    rows={6}
                    placeholder="Descreva o problema, quando começou e o que você já tentou."
                  />
                </label>
                <div className="form-grid">
                  <label>
                    Categoria
                    <select name="category">
                      {Object.entries(categories).map(([value, label]) => (
                        <option value={value} key={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Prioridade
                    <select name="priority" defaultValue="media">
                      {Object.entries(priorities).map(([value, label]) => (
                        <option value={value} key={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="form-footer">
                  <span>O chamado será vinculado à sua conta.</span>
                  <button className="primary" disabled={busy}>
                    {busy ? "Enviando…" : "Enviar chamado"}
                    <ArrowUpRight size={17} />
                  </button>
                </div>
              </form>
            </section>
          ) : (
            <>
              {page === "dashboard" && (
                <section
                  className="overview"
                  aria-label="Resumo da página atual"
                >
                  <div className="overview-lead">
                    <span className="eyebrow">PULSO DO ATENDIMENTO</span>
                    <h2>
                      Um chamado. <br />
                      Uma solução por vez.
                    </h2>
                    <small>
                      Resumo dos {tickets.length} registros desta página
                    </small>
                    <div className="decorative-lines" aria-hidden="true" />
                  </div>
                  {[
                    {
                      label: "Em aberto",
                      states: ["aberto"],
                      note: "Aguardando atendimento",
                    },
                    {
                      label: "Em andamento",
                      states: ["em_atendimento", "aguardando_usuario"],
                      note: "Com atenção da equipe",
                    },
                    {
                      label: "Concluídos",
                      states: ["resolvido", "fechado"],
                      note: "Mais um passo à frente",
                    },
                  ].map((item) => (
                    <div className="metric" key={item.label}>
                      <span>{item.label}</span>
                      <strong>
                        {loading
                          ? "—"
                          : tickets
                              .filter((ticket) =>
                                item.states.includes(ticket.status),
                              )
                              .length.toString()
                              .padStart(2, "0")}
                      </strong>
                      <small>{item.note}</small>
                    </div>
                  ))}
                </section>
              )}
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>
                      {page === "users"
                        ? "Usuários da central"
                        : page === "available"
                          ? "Chamados disponíveis"
                          : "Chamados recentes"}
                    </h2>
                    <span className="muted small">
                      {page === "users"
                        ? "Perfis e acesso"
                        : "Somente chamados permitidos para o seu perfil"}
                    </span>
                  </div>
                  <button
                    className="secondary"
                    disabled={loading || busy}
                    onClick={() => setReload((value) => value + 1)}
                  >
                    <RefreshCw size={15} />
                    Atualizar
                  </button>
                </div>
                <div className="toolbar">
                  <label className="search">
                    <Search size={18} />
                    <input
                      aria-label={
                        page === "users"
                          ? "Buscar usuários nesta página"
                          : "Buscar chamados nesta página"
                      }
                      placeholder={
                        page === "users"
                          ? "Buscar por e-mail ou número…"
                          : "Buscar por título, número ou categoria…"
                      }
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </label>
                  {page !== "users" && (
                    <select
                      aria-label="Filtrar status"
                      value={filter}
                      onChange={(event) => setFilter(event.target.value)}
                    >
                      <option value="">Todos os status</option>
                      {Object.entries(statuses).map(([value, label]) => (
                        <option value={value} key={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                {loading ? (
                  <div
                    className="skeletons"
                    role="status"
                    aria-label="Carregando registros"
                  >
                    {[1, 2, 3, 4].map((i) => (
                      <div className="skeleton" key={i} />
                    ))}
                  </div>
                ) : error && total === 0 ? (
                  <div className="empty">
                    <h3>Dados indisponíveis.</h3>
                    <p>
                      Use Atualizar para tentar carregar os registros novamente.
                    </p>
                  </div>
                ) : page === "users" ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Usuário</th>
                          <th>Perfil</th>
                          <th>Acesso</th>
                          <th>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {userResults.map((user) => (
                          <tr key={user.id}>
                            <td>
                              <strong>{user.email}</strong>
                              <small>
                                #{user.id}
                                {user.id === session.id ? " · Você" : ""}
                              </small>
                            </td>
                            <td>
                              <select
                                aria-label={`Perfil de ${user.email}`}
                                value={user.role}
                                disabled={busy}
                                onChange={(event) => {
                                  const value = event.target.value;
                                  void action(
                                    () =>
                                      request(
                                        `/users/${user.id}/role`,
                                        session.token,
                                        "PATCH",
                                        { role: value },
                                      ),
                                    "Perfil atualizado.",
                                    true,
                                  );
                                }}
                              >
                                {Object.entries(roles).map(([value, label]) => (
                                  <option value={value} key={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <span
                                className={`access ${user.is_active ? "" : "inactive"}`}
                              >
                                {user.is_active ? "Ativo" : "Desativado"}
                              </span>
                            </td>
                            <td>
                              <button
                                className="secondary"
                                disabled={busy}
                                onClick={() =>
                                  void action(
                                    () =>
                                      request(
                                        `/users/${user.id}/active`,
                                        session.token,
                                        "PATCH",
                                        { is_active: !user.is_active },
                                      ),
                                    "Acesso atualizado.",
                                    true,
                                  )
                                }
                              >
                                {user.is_active ? "Desativar" : "Ativar"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!userResults.length && <Empty filtered={!!query} />}
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Chamado</th>
                          <th>Status</th>
                          <th>Prioridade</th>
                          <th>Criado em</th>
                          <th>
                            <span className="sr-only">Detalhes</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((ticket) => (
                          <tr key={ticket.id}>
                            <td>
                              <small className="ticket-number">
                                #{String(ticket.id).padStart(4, "0")}{" "}
                                <span>· {categories[ticket.category]}</span>
                              </small>
                              <button
                                className="ticket-title"
                                disabled={busy}
                                onClick={() => void open(ticket)}
                              >
                                {ticket.title}
                              </button>
                            </td>
                            <td>
                              <Badge status={ticket.status} />
                            </td>
                            <td>
                              <span className={`priority ${ticket.priority}`}>
                                <i />
                                {priorities[ticket.priority]}
                              </span>
                            </td>
                            <td className="date-cell">
                              {date(ticket.created_at)}
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={`Abrir chamado ${ticket.id}`}
                                disabled={busy}
                                onClick={() => void open(ticket)}
                              >
                                <ArrowUpRight size={19} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!visible.length && (
                      <Empty filtered={!!(query || filter)} />
                    )}
                  </div>
                )}
                <div className="pagination">
                  <span>
                    {total ? `${offset + 1}–${offset + total}` : "0"} registros
                    · busca e resumo nesta página
                  </span>
                  <div>
                    <button
                      className="icon-button"
                      aria-label="Página anterior"
                      disabled={!offset || loading || busy}
                      onClick={() =>
                        setOffset((value) => Math.max(0, value - limit))
                      }
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <span>{Math.floor(offset / limit) + 1}</span>
                    <button
                      className="icon-button"
                      aria-label="Próxima página"
                      disabled={total < limit || loading || busy}
                      onClick={() => setOffset((value) => value + limit)}
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
              </section>
              {selected && (
                <section
                  className="panel detail-panel"
                  aria-label="Detalhes do chamado"
                >
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">CHAMADO #{selected.id}</span>
                      <h2>{selected.title}</h2>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Fechar detalhes"
                      disabled={busy}
                      onClick={() => setSelected(null)}
                    >
                      <X size={20} />
                    </button>
                  </div>
                  <div className="detail-body">
                    <Badge status={selected.status} />
                    <p className="description">{selected.description}</p>
                    <dl>
                      <div>
                        <dt>Categoria</dt>
                        <dd>{categories[selected.category]}</dd>
                      </div>
                      <div>
                        <dt>Prioridade</dt>
                        <dd>{priorities[selected.priority]}</dd>
                      </div>
                      <div>
                        <dt>Solicitante</dt>
                        <dd>
                          {selected.requester_id
                            ? `#${selected.requester_id}`
                            : "Registro histórico"}
                        </dd>
                      </div>
                      <div>
                        <dt>Técnico</dt>
                        <dd>
                          {selected.assigned_technician_id
                            ? `#${selected.assigned_technician_id}`
                            : "Não atribuído"}
                        </dd>
                      </div>
                      <div>
                        <dt>Atualizado em</dt>
                        <dd>{date(selected.updated_at)}</dd>
                      </div>
                    </dl>
                    {role === "technician" &&
                      selected.requester_id !== null &&
                      selected.assigned_technician_id === null && (
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            void action(
                              () =>
                                request(
                                  `/tickets/${selected.id}/claim`,
                                  session.token,
                                  "POST",
                                ),
                              "Chamado atribuído a você.",
                            )
                          }
                        >
                          <Headphones size={17} />
                          Assumir chamado
                        </button>
                      )}
                    {(role === "admin" ||
                      (role === "technician" &&
                        selected.assigned_technician_id === session.id)) && (
                      <form
                        className="inline-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          const payload = body(event.currentTarget);
                          void action(
                            () =>
                              request(
                                `/tickets/${selected.id}/status`,
                                session.token,
                                "PATCH",
                                payload,
                              ),
                            "Status atualizado.",
                          );
                        }}
                      >
                        <label>
                          Status
                          <select
                            name="status"
                            key={`${selected.id}-${selected.status}`}
                            defaultValue={selected.status}
                          >
                            {Object.entries(statuses).map(([value, label]) => (
                              <option value={value} key={value}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button className="secondary" disabled={busy}>
                          Salvar status
                        </button>
                      </form>
                    )}
                    {role === "admin" && selected.requester_id !== null && (
                      <form
                        className="inline-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          const value = new FormData(event.currentTarget).get(
                            "technician_id",
                          );
                          void action(
                            () =>
                              request(
                                `/tickets/${selected.id}/assignee`,
                                session.token,
                                "PATCH",
                                { technician_id: value ? Number(value) : null },
                              ),
                            "Atribuição atualizada.",
                          );
                        }}
                      >
                        <label>
                          Número do técnico
                          <input
                            type="number"
                            name="technician_id"
                            min="1"
                            step="1"
                            key={`${selected.id}-${selected.assigned_technician_id}`}
                            defaultValue={selected.assigned_technician_id ?? ""}
                            placeholder="Vazio para remover atribuição"
                          />
                        </label>
                        <button className="secondary" disabled={busy}>
                          Salvar atribuição
                        </button>
                        <small className="muted">
                          Consulte o número em Usuários. A API valida se o
                          técnico está ativo.
                        </small>
                      </form>
                    )}
                  </div>
                </section>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>SmartDesk AI · Central de atendimento</span>
            <span>Organizar. Atender. Resolver.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
function Empty({ filtered }: { filtered: boolean }) {
  return (
    <div className="empty">
      <ClipboardList size={32} strokeWidth={1.3} />
      <h3>
        {filtered ? "Nenhum resultado por aqui." : "Tudo em ordem por aqui."}
      </h3>
      <p>
        {filtered
          ? "Experimente outra busca ou remova os filtros desta página."
          : "Os registros disponíveis para seu perfil aparecem neste espaço."}
      </p>
    </div>
  );
}
