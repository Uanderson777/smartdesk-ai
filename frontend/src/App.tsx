import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Clock3,
  Command,
  Headphones,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Ticket as TicketIcon,
  Users,
  X,
} from "lucide-react";
import { API_BASE, ApiError, api } from "./api";
import type {
  Ticket,
  TicketCategory,
  TicketFilters,
  TicketPriority,
  TicketStatus,
  User,
  UserRole,
} from "./types";

type Page = "dashboard" | "tickets" | "queue" | "users";
interface Session {
  token: string;
  email: string;
  fullName: string | null;
  role: UserRole;
}

const statuses: TicketStatus[] = [
  "aberto",
  "em_atendimento",
  "aguardando_usuario",
  "resolvido",
  "fechado",
];
const priorities: TicketPriority[] = ["critica", "alta", "media", "baixa"];
const categories: TicketCategory[] = ["hardware", "software", "rede", "acesso", "outro"];

const statusLabels: Record<TicketStatus, string> = {
  aberto: "Aberto",
  em_atendimento: "Em atendimento",
  aguardando_usuario: "Aguardando usuário",
  resolvido: "Resolvido",
  fechado: "Fechado",
};
const priorityLabels: Record<TicketPriority, string> = {
  critica: "Crítica",
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
};
const categoryLabels: Record<TicketCategory, string> = {
  hardware: "Hardware",
  software: "Software",
  rede: "Rede",
  acesso: "Acesso",
  outro: "Outro",
};
const roleLabels: Record<UserRole, string> = {
  admin: "Administrador",
  technician: "Técnico",
  requester: "Solicitante",
};
const API_DOCS_URL =
  API_BASE || (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function formatRelative(value: string) {
  const date = new Date(value);
  const diff = Math.max(0, Date.now() - date.getTime());
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `há ${days} d`;
  return formatDate(value);
}

function firstName(fullName: string | null) {
  return fullName?.trim().split(/\s+/)[0] || null;
}

function initials(fullName: string | null) {
  if (!fullName?.trim()) return "?";
  return fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function statusClass(status: TicketStatus) {
  return `status-pill status-${status}`;
}

function priorityClass(priority: TicketPriority) {
  return `priority-dot priority-${priority}`;
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [page, setPage] = useState<Page>("dashboard");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [available, setAvailable] = useState<Ticket[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [filters, setFilters] = useState<TicketFilters>({
    period: "30",
    status: "all",
    priority: "all",
  });
  const [loading, setLoading] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");

  const signOut = useCallback(() => {
    setSession(null);
    setTickets([]);
    setAvailable([]);
    setUsers([]);
    setSelected(null);
    setPage("dashboard");
  }, []);

  const loadWorkspace = useCallback(async (activeSession: Session) => {
    setLoading(true);
    setError("");
    try {
      const [ticketRows, queueRows, userRows] = await Promise.all([
        api.listTickets(activeSession.token),
        activeSession.role === "admin" || activeSession.role === "technician"
          ? api.listAvailableTickets(activeSession.token)
          : Promise.resolve([]),
        activeSession.role === "admin"
          ? api.listUsers(activeSession.token)
          : Promise.resolve([]),
      ]);
      setTickets(ticketRows);
      setAvailable(queueRows);
      setUsers(userRows);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        signOut();
        setError("Sua sessão expirou. Entre novamente.");
      } else {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Não foi possível carregar os dados da API.",
        );
      }
    } finally {
      setLoading(false);
    }
  }, [signOut]);

  useEffect(() => {
    if (session) void loadWorkspace(session);
  }, [session, refreshKey, loadWorkspace]);

  useEffect(() => {
    if (!selected) return;
    const updated = tickets.find((ticket) => ticket.id === selected.id);
    if (updated && updated !== selected) setSelected(updated);
  }, [tickets, selected]);

  const filteredTickets = useMemo(() => {
    const now = Date.now();
    return tickets.filter((ticket) => {
      if (filters.status !== "all" && ticket.status !== filters.status) return false;
      if (filters.priority !== "all" && ticket.priority !== filters.priority) return false;
      if (filters.period !== "all") {
        const range = Number(filters.period) * 24 * 60 * 60 * 1000;
        if (now - new Date(ticket.created_at).getTime() > range) return false;
      }
      if (searchTerm) {
        const query = searchTerm.toLocaleLowerCase("pt-BR");
        const searchable = `${ticket.id} ${ticket.title} ${ticket.description} ${ticket.category}`.toLocaleLowerCase("pt-BR");
        if (!searchable.includes(query)) return false;
      }
      return true;
    });
  }, [tickets, filters, searchTerm]);

  const handleLogin = async (email: string, password: string) => {
    setAuthLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api.login(email, password);
      const [user, role] = await Promise.all([
        api.currentUser(result.access_token),
        api.identifyRole(result.access_token),
      ]);
      setSession({
        token: result.access_token,
        email,
        fullName: user.full_name,
        role,
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível autenticar.",
      );
    } finally {
      setAuthLoading(false);
    }
  };

  const handleRegister = async (
    fullName: string,
    email: string,
    password: string,
  ) => {
    setAuthLoading(true);
    setError("");
    try {
      await api.register(fullName, email, password);
      setNotice("Conta criada. Entre com seu e-mail e senha.");
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha no cadastro.");
      return false;
    } finally {
      setAuthLoading(false);
    }
  };

  const withAction = async (action: () => Promise<unknown>, success: string): Promise<boolean> => {
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      setRefreshKey((value) => value + 1);
      return true;
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        signOut();
        setError("Sua sessão expirou. Entre novamente.");
      } else {
        setError(
          requestError instanceof Error ? requestError.message : "A operação falhou.",
        );
      }
      return false;
    }
  };

  if (!session) {
    return (
      <LoginScreen
        error={error}
        notice={notice}
        loading={authLoading}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
    );
  }

  const navigation = [
    { key: "dashboard" as const, label: "Visão geral", icon: LayoutDashboard },
    { key: "tickets" as const, label: "Chamados", icon: ClipboardList, count: tickets.length },
    ...(session.role !== "requester"
      ? [{ key: "queue" as const, label: "Fila de atendimento", icon: Headphones, count: available.length }]
      : []),
    ...(session.role === "admin"
      ? [{ key: "users" as const, label: "Usuários", icon: Users }]
      : []),
  ];

  const title =
    page === "dashboard"
      ? "Visão geral"
      : page === "tickets"
        ? "Chamados"
        : page === "queue"
          ? "Fila de atendimento"
          : "Gestão de usuários";

  return (
    <div className="app-shell">
      {mobileNavOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Fechar menu"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><LifeBuoy size={23} strokeWidth={2.2} /></div>
          <div className="brand-copy">
            <strong>SmartDesk</strong>
            <span>AI SERVICE DESK</span>
          </div>
          <button className="icon-button sidebar-close" onClick={() => setMobileNavOpen(false)} aria-label="Fechar menu">
            <X size={18} />
          </button>
        </div>

        <div className="workspace-switch">
          <div className="workspace-icon"><Command size={17} /></div>
          <div><strong>Workspace</strong><span>Operações de suporte</span></div>
          <ChevronDown size={16} className="muted-icon" />
        </div>

        <nav className="side-nav" aria-label="Navegação principal">
          <span className="nav-caption">MENU PRINCIPAL</span>
          {navigation.map(({ key, label, icon: Icon, count }) => (
            <button
              key={key}
              className={`nav-item ${page === key ? "nav-active" : ""}`}
              onClick={() => { setPage(key); setMobileNavOpen(false); }}
            >
              <Icon size={18} strokeWidth={1.9} />
              <span>{label}</span>
              {count !== undefined && <span className="nav-count">{count}</span>}
            </button>
          ))}
          <span className="nav-caption nav-caption-spaced">SUPORTE</span>
          <a className="nav-item nav-link" href={`${API_DOCS_URL}/docs`} target="_blank" rel="noreferrer">
            <CircleHelp size={18} strokeWidth={1.9} />
            <span>Documentação da API</span>
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="plan-card">
            <div className="plan-icon"><Sparkles size={16} /></div>
            <strong>Central de suporte</strong>
            <p>Acompanhe chamados e mantenha sua equipe em sintonia.</p>
            <span className="plan-tag">SMARTDESK AI</span>
          </div>
          <div className="sidebar-user">
            <div className="avatar avatar-sidebar">{initials(session.fullName)}</div>
            <div className="sidebar-user-copy">
              <strong>{session.fullName || "Nome não informado"}</strong>
              <span>{roleLabels[session.role]}</span>
            </div>
            <button className="icon-button logout-button" title="Sair" aria-label="Sair" onClick={signOut}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Abrir menu">
              <Menu size={20} />
            </button>
            <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
          </div>
          <div className="topbar-actions">
            <div className="search-box">
              <Search size={16} />
              <input
                aria-label="Buscar chamado"
                placeholder="Buscar chamado..."
                value={searchTerm}
                onChange={(event) => { setSearchTerm(event.target.value.trimStart()); setPage("tickets"); }}
              />
              <kbd>⌘ K</kbd>
            </div>
            <div className="topbar-divider" />
            <div className="topbar-profile">
              <div className="avatar avatar-top">{initials(session.fullName)}</div>
              <div><strong>{session.fullName || "Nome não informado"}</strong><span>{roleLabels[session.role]}</span></div>
              <ChevronDown size={15} />
            </div>
          </div>
        </header>

        <section className="page-content">
          {(error || notice) && (
            <div className={`feedback ${error ? "feedback-error" : "feedback-success"}`} role="status">
              {error ? <CircleHelp size={17} /> : <Check size={17} />}
              <span>{error || notice}</span>
              <button className="icon-button" aria-label="Fechar aviso" onClick={() => { setError(""); setNotice(""); }}><X size={16} /></button>
            </div>
          )}

          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="live-dot" /> PAINEL DE OPERAÇÕES</div>
              <h1>{page === "dashboard" ? (
                firstName(session.fullName)
                  ? <>Bom dia, <span>{firstName(session.fullName)}</span>!</>
                  : "Bom dia!"
              ) : title}</h1>
              <p>{page === "dashboard" ? "Acompanhe o que está acontecendo com sua equipe hoje." : pageDescription(page, session.role)}</p>
            </div>
            <div className="heading-actions">
              <button className="button button-secondary" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading}>
                <RefreshCw size={16} className={loading ? "spin" : ""} /> Atualizar
              </button>
              {(session.role === "requester" || session.role === "admin") && (
                <button className="button button-primary" onClick={() => setCreateOpen(true)}>
                  <Plus size={17} /> Novo chamado
                </button>
              )}
            </div>
          </div>

          {page !== "users" && (
            <FilterBar filters={filters} setFilters={setFilters} />
          )}

          {loading && tickets.length === 0 ? (
            <div className="loading-panel"><span className="loader" /> Carregando dados reais da API...</div>
          ) : page === "dashboard" ? (
            <Dashboard
              tickets={filteredTickets}
              allCount={tickets.length}
              availableCount={available.length}
              role={session.role}
              onOpen={setSelected}
              onNavigate={setPage}
              onClaim={(ticketId) => void withAction(() => api.claimTicket(session.token, ticketId), "Chamado assumido com sucesso.")}
            />
          ) : page === "tickets" ? (
            <TicketList
              tickets={filteredTickets}
              role={session.role}
              onOpen={setSelected}
              onClaim={(ticketId) => void withAction(() => api.claimTicket(session.token, ticketId), "Chamado assumido com sucesso.")}
            />
          ) : page === "queue" ? (
            <QueuePage
              tickets={available.filter((ticket) => {
                if (filters.priority !== "all" && ticket.priority !== filters.priority) return false;
                if (filters.status !== "all" && ticket.status !== filters.status) return false;
                if (filters.period !== "all" && Date.now() - new Date(ticket.created_at).getTime() > Number(filters.period) * 86_400_000) return false;
                return true;
              })}
              role={session.role}
              onOpen={setSelected}
              onClaim={(ticketId) => void withAction(() => api.claimTicket(session.token, ticketId), "Chamado assumido com sucesso.")}
            />
          ) : (
            <UsersPage
              users={users}
              onRoleChange={async (userId, role) => {
                const updated = await withAction(() => api.updateUserRole(session.token, userId, role), "Perfil atualizado.");
                if (updated && users.find((user) => user.id === userId)?.email === session.email) {
                  setSession((current) => current ? { ...current, role } : current);
                  if (role !== "admin") setPage("dashboard");
                }
              }}
              onActiveChange={(userId, active) => void withAction(() => api.updateUserActive(session.token, userId, active), active ? "Usuário reativado." : "Usuário desativado.")}
            />
          )}
        </section>
      </main>

      {createOpen && (
        <CreateTicketModal
          onClose={() => setCreateOpen(false)}
          onSubmit={async (input) => {
            if (!session) return;
            const created = await withAction(() => api.createTicket(session.token, input), "Chamado criado com sucesso.");
            if (created) setCreateOpen(false);
          }}
        />
      )}
      {selected && session && (
        <TicketDetail
          ticket={selected}
          role={session.role}
          users={users}
          onClose={() => setSelected(null)}
          onStatusChange={(status) => void withAction(() => api.updateStatus(session.token, selected.id, status), "Status atualizado.")}
          onAssigneeChange={(technicianId) => void withAction(() => api.assignTicket(session.token, selected.id, technicianId), "Atribuição atualizada.")}
        />
      )}
    </div>
  );
}

function pageDescription(page: Page, role: UserRole) {
  if (page === "tickets") return "Acompanhe os chamados disponíveis para o seu perfil.";
  if (page === "queue") return role === "admin" ? "Chamados aguardando atribuição para atendimento." : "Assuma um chamado disponível para começar o atendimento.";
  if (page === "users") return "Gerencie perfis e o acesso dos usuários do Service Desk.";
  return "Indicadores e atividade recente dos chamados.";
}

function FilterBar({
  filters,
  setFilters,
}: {
  filters: TicketFilters;
  setFilters: (next: TicketFilters) => void;
}) {
  return (
    <div className="filter-bar">
      <div className="filter-label"><SlidersHorizontal size={16} /><span>Filtros</span></div>
      <label className="filter-control">
        <span>Período</span>
        <select value={filters.period} onChange={(event) => setFilters({ ...filters, period: event.target.value as TicketFilters["period"] })}>
          <option value="7">Últimos 7 dias</option>
          <option value="30">Últimos 30 dias</option>
          <option value="90">Últimos 90 dias</option>
          <option value="all">Todo o período</option>
        </select>
      </label>
      <label className="filter-control">
        <span>Status</span>
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value as TicketFilters["status"] })}>
          <option value="all">Todos os status</option>
          {statuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}
        </select>
      </label>
      <label className="filter-control">
        <span>Prioridade</span>
        <select value={filters.priority} onChange={(event) => setFilters({ ...filters, priority: event.target.value as TicketFilters["priority"] })}>
          <option value="all">Todas as prioridades</option>
          {priorities.map((priority) => <option key={priority} value={priority}>{priorityLabels[priority]}</option>)}
        </select>
      </label>
      <button className="filter-reset" onClick={() => setFilters({ period: "30", status: "all", priority: "all" })}>Limpar</button>
    </div>
  );
}

function Dashboard({
  tickets,
  allCount,
  availableCount,
  role,
  onOpen,
  onNavigate,
  onClaim,
}: {
  tickets: Ticket[];
  allCount: number;
  availableCount: number;
  role: UserRole;
  onOpen: (ticket: Ticket) => void;
  onNavigate: (page: Page) => void;
  onClaim: (ticketId: number) => void;
}) {
  const openCount = tickets.filter((ticket) => ticket.status === "aberto").length;
  const inProgressCount = tickets.filter((ticket) => ticket.status === "em_atendimento").length;
  const resolvedCount = tickets.filter((ticket) => ticket.status === "resolvido" || ticket.status === "fechado").length;
  const latest = [...tickets].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 6);

  return (
    <>
      <div className="metrics-grid">
        <MetricCard title="Total de chamados" value={tickets.length} note="Dados retornados pela API" icon={TicketIcon} color="blue" />
        <MetricCard title="Abertos" value={openCount} note="Aguardando atendimento" icon={Clock3} color="amber" />
        <MetricCard title="Em atendimento" value={inProgressCount} note="Em andamento pela equipe" icon={Activity} color="violet" />
        <MetricCard title="Resolvidos" value={resolvedCount} note="Resolvidos ou fechados" icon={ShieldCheck} color="green" />
      </div>

      <div className="dashboard-grid">
        <section className="panel trend-panel">
          <PanelHeading title="Volume de chamados" subtitle="Aberturas nos últimos 7 dias" badge="POR DATA DE ABERTURA" />
          <TrendChart tickets={tickets} />
        </section>
        <section className="panel status-panel">
          <PanelHeading title="Visão por status" subtitle="Distribuição no período filtrado" />
          <StatusChart tickets={tickets} />
        </section>
      </div>

      <div className="bottom-grid">
        <section className="panel recent-panel">
          <PanelHeading
            title="Chamados recentes"
            subtitle="Atividade mais recente no seu escopo"
            action={<button className="text-button" onClick={() => onNavigate("tickets")}>Ver todos <ChevronRight size={15} /></button>}
          />
          <TicketTable tickets={latest} role={role} onOpen={onOpen} onClaim={onClaim} compact />
        </section>
        <section className="panel priority-panel">
          <PanelHeading title="Por prioridade" subtitle="Chamados no período" />
          <PriorityBreakdown tickets={tickets} />
          <div className="mini-summary">
            <span><i className="summary-dot summary-open" /> Escopo atual</span>
            <strong>{allCount} chamados</strong>
          </div>
          {role !== "requester" && (
            <button className="queue-callout" onClick={() => onNavigate("queue")}>
              <div className="queue-callout-icon"><Headphones size={17} /></div>
              <div><strong>{availableCount} disponíveis</strong><span>Na fila de atendimento</span></div>
              <ChevronRight size={17} />
            </button>
          )}
        </section>
      </div>
    </>
  );
}

function MetricCard({
  title,
  value,
  note,
  icon: Icon,
  color,
  trend,
}: {
  title: string;
  value: number;
  note: string;
  icon: typeof TicketIcon;
  color: string;
  trend?: number | null;
}) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span>{title}</span>
        <span className={`metric-icon metric-${color}`}><Icon size={19} strokeWidth={1.9} /></span>
      </div>
      <div className="metric-value">{value.toLocaleString("pt-BR")}</div>
      <div className="metric-foot">
        {trend !== undefined ? (
          trend === null ? <span className="metric-neutral">Sem período anterior</span> : (
            <span className={trend >= 0 ? "metric-up" : "metric-down"}>
              {trend >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {Math.abs(trend)}% vs. período anterior
            </span>
          )
        ) : <span className="metric-note">{note}</span>}
      </div>
    </article>
  );
}

function PanelHeading({
  title,
  subtitle,
  badge,
  action,
}: {
  title: string;
  subtitle: string;
  badge?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-heading">
      <div><h2>{title}</h2><p>{subtitle}</p></div>
      {badge && <span className="panel-badge">{badge}</span>}
      {action}
    </div>
  );
}

function TrendChart({ tickets }: { tickets: Ticket[] }) {
  const days = useMemo(() => {
    const today = new Date();
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (6 - index));
      const key = date.toLocaleDateString("en-CA");
      const count = tickets.filter((ticket) => new Date(ticket.created_at).toLocaleDateString("en-CA") === key).length;
      return { label: new Intl.DateTimeFormat("pt-BR", { weekday: "short" }).format(date).replace(".", ""), count };
    });
  }, [tickets]);
  const max = Math.max(...days.map((day) => day.count), 1);
  return (
    <div className="trend-chart" role="img" aria-label="Gráfico de chamados criados nos últimos sete dias">
      <div className="chart-y-labels"><span>{max}</span><span>{Math.round(max / 2)}</span><span>0</span></div>
      <div className="chart-columns">
        <div className="chart-grid-lines"><i /><i /><i /></div>
        {days.map((day, index) => (
          <div className="chart-column" key={`${day.label}-${index}`}>
            <span className="chart-bar-value">{day.count || ""}</span>
            <div className={`chart-bar ${index === 6 ? "chart-bar-today" : ""}`} style={{ height: `${Math.max((day.count / max) * 100, day.count ? 8 : 2)}%` }} title={`${day.count} chamado(s)`} />
            <span className="chart-x-label">{day.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusChart({ tickets }: { tickets: Ticket[] }) {
  const colors: Record<TicketStatus, string> = {
    aberto: "#f5a524",
    em_atendimento: "#7768f6",
    aguardando_usuario: "#3d9bd9",
    resolvido: "#35b887",
    fechado: "#93a0b5",
  };
  const counts = statuses.map((status) => ({
    status,
    count: tickets.filter((ticket) => ticket.status === status).length,
  }));
  const total = tickets.length;
  let running = 0;
  const gradient = total
    ? counts.map(({ status, count }) => {
        const start = (running / total) * 100;
        running += count;
        return `${colors[status]} ${start}% ${(running / total) * 100}%`;
      }).join(", ")
    : "#e9edf4 0% 100%";
  return (
    <div className="status-chart-wrap">
      <div className="donut" style={{ background: `conic-gradient(${gradient})` }}>
        <div className="donut-hole"><strong>{total}</strong><span>chamados</span></div>
      </div>
      <div className="status-legend">
        {counts.map(({ status, count }) => (
          <div className="legend-row" key={status}>
            <span><i style={{ backgroundColor: colors[status] }} />{statusLabels[status]}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function PriorityBreakdown({ tickets }: { tickets: Ticket[] }) {
  const counts = priorities.map((priority) => ({
    priority,
    count: tickets.filter((ticket) => ticket.priority === priority).length,
  }));
  const max = Math.max(...counts.map((item) => item.count), 1);
  return (
    <div className="priority-breakdown">
      {counts.map(({ priority, count }) => (
        <div className="priority-row" key={priority}>
          <div className="priority-row-label"><span className={priorityClass(priority)} />{priorityLabels[priority]}<strong>{count}</strong></div>
          <div className="progress-track"><span className={`progress-${priority}`} style={{ width: `${(count / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function TicketTable({
  tickets,
  role,
  onOpen,
  onClaim,
  compact = false,
}: {
  tickets: Ticket[];
  role: UserRole;
  onOpen: (ticket: Ticket) => void;
  onClaim: (ticketId: number) => void;
  compact?: boolean;
}) {
  if (!tickets.length) {
    return <div className="empty-state"><div className="empty-icon"><TicketIcon size={20} /></div><strong>Nenhum chamado neste filtro</strong><span>Quando houver chamados correspondentes, eles aparecerão aqui.</span></div>;
  }
  return (
    <div className={`table-scroll ${compact ? "table-compact" : ""}`}>
      <table className="ticket-table">
        <thead><tr><th>CHAMADO</th><th>PRIORIDADE</th><th>STATUS</th><th>ATUALIZADO</th><th /></tr></thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td>
                <button className="ticket-title-button" onClick={() => onOpen(ticket)}>
                  <span className={`ticket-id ticket-id-${ticket.priority}`}>#{ticket.id.toString().padStart(4, "0")}</span>
                  <span className="ticket-title-copy"><strong>{ticket.title}</strong><small>{categoryLabels[ticket.category]} · {ticket.requester_id === null ? "Registro histórico" : `Solicitante #${ticket.requester_id}`}</small></span>
                </button>
              </td>
              <td><span className="priority-label"><i className={priorityClass(ticket.priority)} />{priorityLabels[ticket.priority]}</span></td>
              <td><span className={statusClass(ticket.status)}><i />{statusLabels[ticket.status]}</span></td>
              <td><span className="updated-time">{formatRelative(ticket.updated_at)}</span></td>
              <td className="table-actions">
                {role === "technician" && ticket.assigned_technician_id === null && ticket.requester_id !== null
                  ? <button className="small-action" onClick={() => onClaim(ticket.id)}>Assumir</button>
                  : <button className="icon-button row-open" onClick={() => onOpen(ticket)} aria-label={`Abrir chamado ${ticket.id}`}><ChevronRight size={17} /></button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TicketList({
  tickets,
  role,
  onOpen,
  onClaim,
}: {
  tickets: Ticket[];
  role: UserRole;
  onOpen: (ticket: Ticket) => void;
  onClaim: (ticketId: number) => void;
}) {
  return (
    <section className="panel list-panel">
      <PanelHeading title="Todos os chamados" subtitle={`${tickets.length} registro(s) no filtro atual`} badge="DADOS DA API" />
      <TicketTable tickets={tickets} role={role} onOpen={onOpen} onClaim={onClaim} />
    </section>
  );
}

function QueuePage({
  tickets,
  role,
  onOpen,
  onClaim,
}: {
  tickets: Ticket[];
  role: UserRole;
  onOpen: (ticket: Ticket) => void;
  onClaim: (ticketId: number) => void;
}) {
  return (
    <section className="panel list-panel">
      <PanelHeading title="Chamados disponíveis" subtitle="Chamados sem técnico atribuído retornados pela API." badge={`${tickets.length} NA FILA`} />
      <TicketTable tickets={tickets} role={role} onOpen={onOpen} onClaim={onClaim} />
    </section>
  );
}

function UsersPage({
  users,
  onRoleChange,
  onActiveChange,
}: {
  users: User[];
  onRoleChange: (userId: number, role: UserRole) => void;
  onActiveChange: (userId: number, active: boolean) => void;
}) {
  return (
    <section className="panel list-panel">
      <PanelHeading title="Usuários" subtitle="Perfis e estado das contas gerenciados pela API." badge={`${users.length} USUÁRIOS`} />
      {!users.length ? <div className="empty-state"><strong>Nenhum usuário retornado</strong></div> : (
        <div className="table-scroll">
          <table className="ticket-table users-table">
            <thead><tr><th>USUÁRIO</th><th>PERFIL</th><th>CONTA</th><th>AÇÕES</th></tr></thead>
            <tbody>{users.map((user) => (
              <tr key={user.id}>
                <td><div className="user-cell"><div className="avatar user-avatar">{initials(user.full_name)}</div><span><strong>{user.full_name || "Nome não informado"}</strong><small>{user.email} · Usuário #{user.id}</small></span></div></td>
                <td><select className="inline-select" value={user.role} onChange={(event) => onRoleChange(user.id, event.target.value as UserRole)}><option value="admin">Administrador</option><option value="technician">Técnico</option><option value="requester">Solicitante</option></select></td>
                <td><span className={`account-state ${user.is_active ? "account-active" : "account-inactive"}`}><i />{user.is_active ? "Ativa" : "Desativada"}</span></td>
                <td><button className={`small-action ${user.is_active ? "small-action-muted" : ""}`} onClick={() => onActiveChange(user.id, !user.is_active)}>{user.is_active ? "Desativar" : "Reativar"}</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TicketDetail({
  ticket,
  role,
  users,
  onClose,
  onStatusChange,
  onAssigneeChange,
}: {
  ticket: Ticket;
  role: UserRole;
  users: User[];
  onClose: () => void;
  onStatusChange: (status: TicketStatus) => void;
  onAssigneeChange: (technicianId: number | null) => void;
}) {
  const canUpdate = role === "admin" || (role === "technician" && ticket.assigned_technician_id !== null);
  const technicians = users.filter((user) => user.role === "technician" && user.is_active);
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <div className="drawer-header">
          <div><span className="eyebrow">CHAMADO #{ticket.id.toString().padStart(4, "0")}</span><button className="icon-button" onClick={onClose} aria-label="Fechar detalhes"><X size={20} /></button></div>
          <h2 id="detail-title">{ticket.title}</h2>
          <div className="drawer-badges"><span className={statusClass(ticket.status)}><i />{statusLabels[ticket.status]}</span><span className="priority-label"><i className={priorityClass(ticket.priority)} />{priorityLabels[ticket.priority]}</span></div>
        </div>
        <div className="drawer-body">
          <div className="detail-section"><h3>Descrição</h3><p className="ticket-description">{ticket.description}</p></div>
          <div className="detail-info-grid">
            <InfoCell label="Categoria" value={categoryLabels[ticket.category]} />
            <InfoCell label="Solicitante" value={ticket.requester_id === null ? "Registro histórico" : `Usuário #${ticket.requester_id}`} />
            <InfoCell label="Criado em" value={formatDate(ticket.created_at)} />
            <InfoCell label="Última atualização" value={formatDate(ticket.updated_at)} />
            <InfoCell label="Técnico" value={ticket.assigned_technician_id === null ? "Não atribuído" : `Usuário #${ticket.assigned_technician_id}`} />
          </div>
          <div className="history-note"><Clock3 size={17} /><span>O backend disponibiliza apenas a última atualização do chamado; não há trilha de eventos/status para exibir um histórico detalhado.</span></div>
          {role === "admin" && ticket.requester_id !== null && (
            <div className="detail-section"><h3>Atribuição do técnico</h3><select className="drawer-select" value={ticket.assigned_technician_id ?? ""} onChange={(event) => onAssigneeChange(event.target.value ? Number(event.target.value) : null)}><option value="">Sem técnico atribuído</option>{technicians.map((user) => <option key={user.id} value={user.id}>{user.email}</option>)}</select></div>
          )}
          {canUpdate && (
            <div className="detail-section"><h3>Atualizar status</h3><select className="drawer-select" value={ticket.status} onChange={(event) => onStatusChange(event.target.value as TicketStatus)}>{statuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}</select></div>
          )}
        </div>
      </section>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return <div className="info-cell"><span>{label}</span><strong>{value}</strong></div>;
}

function CreateTicketModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (input: { title: string; description: string; category: TicketCategory; priority: TicketPriority }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<TicketCategory>("software");
  const [priority, setPriority] = useState<TicketPriority>("media");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({ title, description, category, priority });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Não foi possível criar o chamado.");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <form className="form-modal" onSubmit={(event) => void submit(event)}>
        <div className="modal-heading"><div><span className="eyebrow">NOVO REGISTRO</span><h2>Abrir chamado</h2><p>Descreva o que precisa de suporte.</p></div><button type="button" className="icon-button" onClick={onClose} aria-label="Fechar"><X size={20} /></button></div>
        {error && <div className="inline-error">{error}</div>}
        <label className="form-field"><span>Título</span><input minLength={5} maxLength={160} required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ex.: Não consigo acessar o sistema" /></label>
        <label className="form-field"><span>Descrição</span><textarea minLength={10} maxLength={5000} required rows={4} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Inclua detalhes que ajudem a equipe a entender o problema..." /></label>
        <div className="form-row">
          <label className="form-field"><span>Categoria</span><select value={category} onChange={(event) => setCategory(event.target.value as TicketCategory)}>{categories.map((item) => <option key={item} value={item}>{categoryLabels[item]}</option>)}</select></label>
          <label className="form-field"><span>Prioridade</span><select value={priority} onChange={(event) => setPriority(event.target.value as TicketPriority)}>{priorities.map((item) => <option key={item} value={item}>{priorityLabels[item]}</option>)}</select></label>
        </div>
        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button className="button button-primary" disabled={submitting}><Plus size={16} />{submitting ? "Enviando..." : "Criar chamado"}</button></div>
      </form>
    </div>
  );
}

function LoginScreen({
  error,
  notice,
  loading,
  onLogin,
  onRegister,
}: {
  error: string;
  notice: string;
  loading: boolean;
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (
    fullName: string,
    email: string,
    password: string,
  ) => Promise<boolean>;
}) {
  const [registerMode, setRegisterMode] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <main className="auth-page">
      <div className="auth-visual">
        <div className="auth-visual-glow" />
        <div className="auth-brand"><div className="brand-mark"><LifeBuoy size={23} /></div><strong>SmartDesk<span> AI</span></strong></div>
        <div className="auth-visual-content">
          <span className="auth-kicker"><span className="live-dot" /> SERVICE DESK INTELIGENTE</span>
          <h1>Suporte organizado.<br /><span>Experiências melhores.</span></h1>
          <p>Uma visão clara de cada solicitação, do primeiro contato à resolução.</p>
          <div className="auth-visual-stats"><div><strong>Atendimento</strong><span>com contexto</span></div><div><strong>Equipe</strong><span>em sintonia</span></div><div><strong>Chamados</strong><span>acompanhados</span></div></div>
        </div>
        <div className="auth-visual-footer"><span>SMARTDESK AI</span><span>PLATAFORMA DE SUPORTE</span></div>
      </div>
      <div className="auth-form-side">
        <div className="auth-form-wrap">
          <span className="auth-form-overline">{registerMode ? "COMECE POR AQUI" : "BEM-VINDO DE VOLTA"}</span>
          <h2>{registerMode ? "Crie sua conta" : "Acesse seu workspace"}</h2>
          <p>{registerMode ? "Cadastre-se para abrir e acompanhar chamados." : "Entre para acompanhar suas operações de suporte."}</p>
          {error && <div className="feedback feedback-error auth-feedback"><CircleHelp size={17} /><span>{error}</span></div>}
          {notice && <div className="feedback feedback-success auth-feedback"><Check size={17} /><span>{notice}</span></div>}
          <form onSubmit={(event) => {
            event.preventDefault();
            if (registerMode) {
              void onRegister(fullName, email, password).then((success) => { if (success) setRegisterMode(false); });
            } else {
              void onLogin(email, password);
            }
          }}>
            {registerMode && (
              <label className="form-field">
                <span>Nome completo</span>
                <input
                  type="text"
                  autoComplete="name"
                  maxLength={160}
                  required
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Seu nome completo"
                />
              </label>
            )}
            <label className="form-field"><span>E-mail</span><input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="voce@empresa.com" /></label>
            <label className="form-field"><span>Senha</span><input type="password" autoComplete={registerMode ? "new-password" : "current-password"} minLength={registerMode ? 8 : 1} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Sua senha" /></label>
            <button className="button button-primary auth-submit" disabled={loading}>{loading ? "Aguarde..." : registerMode ? "Criar conta" : "Entrar no workspace"}<ChevronRight size={17} /></button>
          </form>
          <div className="auth-switch">{registerMode ? "Já tem uma conta?" : "Ainda não tem uma conta?"}<button onClick={() => { setRegisterMode(!registerMode); }}>{registerMode ? "Fazer login" : "Criar conta"}</button></div>
          <div className="auth-security"><ShieldCheck size={16} /><span>Conexão autenticada · sessão protegida em memória</span></div>
        </div>
        <span className="auth-copyright">© 2026 SmartDesk AI · Service Desk</span>
      </div>
    </main>
  );
}

export default App;
