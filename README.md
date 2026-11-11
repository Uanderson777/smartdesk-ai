# SmartDesk AI

Aplicação de Service Desk com API REST e painel web para autenticação,
gerenciamento de usuários e atendimento de chamados.

- **Implantação informada:** https://smartdesk-ai-1swde3w2f-uanderson777s-projects.vercel.app
  (status Production/Preview não confirmado; veja [Publicação](#publicação-vercel-render-e-postgresql))
- **Repositório:** https://github.com/Uanderson777/smartdesk-ai
- **API:** https://smartdesk-ai-0rev.onrender.com
- **Verificação da API:** https://smartdesk-ai-0rev.onrender.com/health

## Funcionalidades implementadas

- Cadastro público de solicitantes e login com token JWT.
- Seleção de empresa no login quando a conta tem mais de uma associação ativa.
- Perfis por empresa: administrador, técnico e solicitante.
- Isolamento de chamados e usuários pelo tenant ativo.
- Criação, consulta, listagem paginada, atribuição, fila e atualização de status
  dos chamados.
- Painel com filtros, indicadores, busca e telas diferentes conforme o perfil.
- Administração de perfis e ativações de usuários, sem exclusão definitiva.
- Triagem opcional de chamados pela Gemini API: sugestão de categoria,
  prioridade, justificativa e rascunho de resposta para revisão. A sugestão não
  atualiza o chamado nem envia a resposta.
- Documentação interativa da API em `/docs`.

Não há envio de respostas ao solicitante, trilha de eventos dos chamados,
refresh token, cobrança ou pagamentos implementados.

## Tecnologias

- Python 3.13, FastAPI, Pydantic e SQLAlchemy
- Alembic para migrations
- PostgreSQL em produção; SQLite para desenvolvimento e testes
- JWT (HS256) e hashes de senha Argon2id (`pwdlib`)
- React 18, TypeScript, Vite e Axios
- Pytest e GitHub Actions
- Gemini API opcional, chamada somente pelo backend

## Estrutura

```text
app/                 API, autenticação, autorização, banco e integração Gemini
migrations/          Histórico de migrations Alembic
tests/               Testes de API, migrations e integração de IA
frontend/src/        Aplicação React e cliente HTTP
Dockerfile           Imagem do backend para o Render
```

## Desenvolvimento local no Windows

### Requisitos

- Windows com PowerShell
- Python 3.13
- Node.js e npm compatíveis com Vite 6
- Git

Clone o repositório:

```powershell
git clone https://github.com/Uanderson777/smartdesk-ai.git
Set-Location smartdesk-ai
```

Crie o ambiente Python e instale as dependências:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se a política do PowerShell impedir a ativação do ambiente, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Defina uma chave JWT de desenvolvimento no terminal atual. Não reutilize essa
chave em produção:

```powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Sem `DATABASE_URL`, o backend usa `sqlite:///./smartdesk.db` localmente. Para
usar PostgreSQL local, defina uma URL de conexão para um banco de
desenvolvimento que já exista:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:senha@localhost:5432/smartdesk"
```

As migrations são aplicadas quando a API inicia. Para iniciar o backend:

```powershell
python -m uvicorn app.main:app --reload
```

A API local fica em `http://127.0.0.1:8000`; a documentação fica em
`http://127.0.0.1:8000/docs` e o health check em
`http://127.0.0.1:8000/health`.

### Primeiro administrador local

O cadastro público cria somente solicitantes. Para criar ou promover um
administrador, execute explicitamente:

```powershell
python -m app.bootstrap_admin admin@example.com
```

O comando exige exatamente uma empresa e interrompe se já houver administrador
ativo. Para uma conta nova, solicita a senha de forma interativa. A aplicação
nunca cria um administrador automaticamente.

### Frontend local

Em outro terminal PowerShell, na raiz do repositório:

```powershell
Set-Location frontend
npm install
npm run dev
```

Abra `http://127.0.0.1:5173`. Em desenvolvimento, chamadas relativas `/api`
usam o proxy do Vite para `http://127.0.0.1:8000`. Se o backend estiver em
outro endereço, defina `SMARTDESK_API_URL` antes de iniciar o Vite:

```powershell
$env:SMARTDESK_API_URL = "http://127.0.0.1:8001"
npm run dev
```

Em produção, o frontend usa exclusivamente a API oficial
`https://smartdesk-ai-0rev.onrender.com`. A URL não é substituída por
`VITE_API_BASE_URL`, evitando que uma variável antiga cadastrada na Vercel
aponte novamente para um serviço Render desativado. No desenvolvimento local,
o proxy do Vite continua usando `SMARTDESK_API_URL` quando configurada.

## Banco de dados e migrations

SQLite é o padrão somente fora do Render. A implantação no Render exige
`DATABASE_URL` apontando para PostgreSQL; o backend rejeita SQLite nesse
ambiente. URLs `postgres://` e `postgresql://` do provedor são normalizadas para
o driver `psycopg`.

As migrations avançam para `head` durante a inicialização. A migração legada
adiciona a empresa inicial, associa os usuários existentes e atribui os
chamados históricos a essa empresa, mantendo os chamados sem solicitante.
As migrations não devem ser revertidas em produção sem um plano específico de
preservação de dados. Não recrie o banco de produção para aplicar alterações.

## Configuração da Gemini API

A integração é opcional. Configure somente no ambiente do backend:

| Variável | Uso |
|---|---|
| `GEMINI_API_KEY` | Chave privada da API Gemini. Sem ela, a triagem responde `503`. |
| `GEMINI_MODEL` | Modelo Gemini; padrão `gemini-2.5-flash`. |

Nunca use nomes `VITE_` para a chave Gemini nem a inclua no frontend. A chave é
enviada pelo servidor no cabeçalho da chamada ao provedor. A triagem requer
autenticação de administrador ou técnico, e o resultado precisa ser revisado
por uma pessoa.

## Testes e build

Na raiz do repositório, com o ambiente Python ativado:

```powershell
pytest -v
```

Os testes usam bancos SQLite temporários/em memória para validar autenticação,
autorização, isolamento, operações administrativas e migrações legadas; não
precisam do PostgreSQL de produção nem de uma chave Gemini real.

Para instalar as dependências e validar o frontend:

```powershell
Set-Location frontend
npm install
npm run build
```

O build executa `tsc --noEmit` e gera os arquivos estáticos em `frontend/dist`.
O workflow do GitHub Actions executa `pytest -v` com Python 3.13 em pushes e
pull requests para `main`.

## Publicação: Vercel, Render e PostgreSQL

### Frontend na Vercel

O frontend é hospedado na Vercel. O link de implantação fornecido é
[smartdesk-ai-1swde3w2f-uanderson777s-projects.vercel.app](https://smartdesk-ai-1swde3w2f-uanderson777s-projects.vercel.app).
Não foi possível confirmar se essa implantação está configurada como Preview ou
Production; portanto, trate-a como referência de implantação, não como domínio
Production definitivo. A Vercel solicita autenticação ao consultar esse endereço
sem uma sessão, e o status não fica verificável publicamente.

Referências administrativas (não são endereços públicos principais para usuários):

- [Projeto no painel da Vercel](https://vercel.com/uanderson777s-projects/smartdesk-ai-app)
- [Detalhes da implantação informada](https://vercel.com/uanderson777s-projects/smartdesk-ai-app/BHKiffKgUkwNRchxSgqaHw5FEpew)

O repositório não contém `vercel.json`; configure o projeto no painel da Vercel:

- Root Directory: `frontend`
- Framework Preset: Vite
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`
Não cadastre `VITE_API_BASE_URL` na Vercel. O frontend de produção já aponta
diretamente para `https://smartdesk-ai-0rev.onrender.com` no código. Se existir
uma variável antiga `VITE_API_BASE_URL` no painel da Vercel, remova-a para
evitar confusão em futuras manutenções.

O endereço Production público deve ser confirmado no painel da Vercel antes de
ser divulgado como URL definitiva. A origem Vercel atualmente incluída por
padrão no CORS é `https://smartdesk-ai-app.vercel.app`; se o domínio Production
confirmado for diferente, configure a origem exata em `CORS_ORIGINS` no Render.
Não adicione domínios Preview sem necessidade.

### API no Render

A API está hospedada em
[smartdesk-ai-0rev.onrender.com](https://smartdesk-ai-0rev.onrender.com), com
[documentação interativa](https://smartdesk-ai-0rev.onrender.com/docs). O código
está no [GitHub](https://github.com/Uanderson777/smartdesk-ai). O [Dockerfile](./Dockerfile)
usa Python 3.13, executa o processo sem privilégios de root e inicia Uvicorn na
porta `PORT` fornecida pelo Render (com fallback local para `8000`). Configure
o serviço para construir a partir desse Dockerfile e use PostgreSQL persistente.

Variáveis do serviço backend:

| Variável | Configuração |
|---|---|
| `DATABASE_URL` | URL privada do PostgreSQL persistente; nunca use SQLite em produção. |
| `JWT_SECRET_KEY` | Segredo aleatório com pelo menos 32 bytes, mantido no cofre de segredos do Render. |
| `CORS_ORIGINS` | Origens exatas adicionais, separadas por vírgula e sem caminhos. O backend sempre inclui `https://smartdesk-ai-app.vercel.app`. |
| `GEMINI_API_KEY` | Opcional; manter exclusivamente no backend. |
| `GEMINI_MODEL` | Opcional; padrão `gemini-2.5-flash`. |
| `PORT` | Injetada pelo Render; não fixe manualmente. |

O backend permite os métodos `GET`, `POST` e `PATCH` e os headers
`Authorization` e `Content-Type`, necessários às rotas existentes. Domínios
Vercel de preview só devem ser adicionados a `CORS_ORIGINS` quando precisarem
de acesso. Não use curingas.

O health check do serviço é `https://smartdesk-ai-0rev.onrender.com/health`.
As migrations são aplicadas durante a inicialização da API. O administrador
inicial deve ser criado manualmente, em uma execução controlada com acesso ao
banco e às variáveis do serviço, usando `python -m app.bootstrap_admin
admin@example.com`. Não execute esse comando em cada deploy.

## Endpoints implementados

| Método | Endpoint | Acesso |
|---|---|---|
| `GET` | `/` | Público; informações do serviço. |
| `GET` | `/health` | Público; health check. |
| `POST` | `/api/v1/auth/register` | Público; cria solicitante. |
| `POST` | `/api/v1/auth/login` | Público; autentica; aceita `company_id` quando necessário. |
| `GET` | `/api/v1/auth/me` | Autenticado; dados do usuário atual. |
| `GET` | `/api/v1/users` | Administrador; lista usuários do tenant ativo. |
| `PATCH` | `/api/v1/users/{user_id}/role` | Administrador; altera perfil no tenant ativo. |
| `PATCH` | `/api/v1/users/{user_id}/active` | Administrador; ativa ou desativa associação. |
| `POST` | `/api/v1/tickets` | Solicitante ou administrador; cria chamado. |
| `GET` | `/api/v1/tickets` | Autenticado; lista chamados permitidos ao perfil. |
| `GET` | `/api/v1/tickets/available` | Técnico ou administrador; lista chamados disponíveis. |
| `GET` | `/api/v1/tickets/{ticket_id}` | Autenticado; consulta chamado dentro do tenant. |
| `POST` | `/api/v1/tickets/{ticket_id}/claim` | Técnico; assume chamado disponível. |
| `PATCH` | `/api/v1/tickets/{ticket_id}/assignee` | Administrador; atribui/remove técnico. |
| `PATCH` | `/api/v1/tickets/{ticket_id}/status` | Técnico atribuído ou administrador; altera status. |
| `POST` | `/api/v1/tickets/{ticket_id}/triage` | Administrador ou técnico; solicita sugestão Gemini. |

Rotas protegidas usam `Authorization: Bearer <token>`. O token tem validade de
30 minutos, permanece somente na memória do frontend e não há refresh token.

## Segurança e limitações conhecidas

- Senhas são armazenadas com Argon2id e não retornadas pelas rotas de usuário.
- A autorização e o escopo do tenant são verificados no backend.
- A chave Gemini não é entregue ao navegador.
- Chamados e usuários não são apagados pela interface de gestão.
- O cadastro público não permite criar contas administrativas.
- Não existe trilha histórica de alterações/status do chamado.
- A triagem da IA gera somente recomendações e rascunhos; não altera nem envia
  respostas automaticamente.
