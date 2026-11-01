# SmartDesk AI

Sistema inteligente de Service Desk desenvolvido com Python e FastAPI.

O SmartDesk AI oferece uma API REST para autenticação, gestão de usuários e
atendimento de chamados com controle de acesso baseado em perfis. O projeto
está em evolução contínua; esta documentação descreve somente o que está
implementado atualmente.

## Tecnologias

- Python 3.13
- FastAPI
- React
- TypeScript
- Vite
- SQLAlchemy
- Alembic
- Pydantic
- SQLite
- PyJWT
- pwdlib com Argon2id
- Pytest

## Requisitos

- Python 3.13
- Git

## Instalação e configuração

Clone o repositório e entre na pasta do projeto:

```bash
git clone https://github.com/Uanderson777/smartdesk-ai.git
cd smartdesk-ai
```

Crie e ative um ambiente virtual.

Windows (PowerShell):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

O banco padrão é `sqlite:///./smartdesk.db`. Para apontar a aplicação a outro
banco compatível com SQLAlchemy, defina `DATABASE_URL` antes de iniciar a API
ou executar o comando de bootstrap.

Configure `JWT_SECRET_KEY` com pelo menos 32 bytes. Gere uma chave forte e
mantenha-a em uma configuração segura do ambiente; não a inclua no código, no
Git ou em mensagens:

Windows (PowerShell):

```powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Linux/macOS:

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Os arquivos `.env` são ignorados pelo Git. Configure variáveis de ambiente em
cada sessão ou use uma solução de gerenciamento de segredos apropriada ao
ambiente de implantação.

## Migrations e primeiro administrador

As migrations do Alembic são aplicadas automaticamente quando a API inicia.
Elas criam ou atualizam as tabelas necessárias, incluindo a associação dos
chamados aos usuários. Chamados existentes são preservados; registros
históricos sem proprietário permanecem com `requester_id` nulo.

Antes do primeiro login administrativo, crie o primeiro administrador:

```bash
python -m app.bootstrap_admin admin@example.com
```

O comando aplica as migrations, solicita a senha de forma interativa caso o
usuário ainda não exista e cria sua conta. Se o usuário já existir, ele pode
ser promovido a administrador. O comando não permite prosseguir quando já
existe um administrador ativo.

## Inicialização da API

Com o ambiente virtual ativado e `JWT_SECRET_KEY` configurada, execute:

```bash
uvicorn app.main:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. A documentação interativa
do FastAPI está em `http://127.0.0.1:8000/docs`.

## Dashboard web

O frontend React + TypeScript fica em `frontend/` e usa o Vite durante o
desenvolvimento. Em um terminal, inicie primeiro a API com a configuração
descrita acima. Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Abra `http://127.0.0.1:5173`. O servidor Vite encaminha as chamadas `/api` para
`http://127.0.0.1:8000`. Se a API estiver em outro endereço, defina
`SMARTDESK_API_URL` antes de iniciar o servidor de desenvolvimento.

Para gerar os arquivos otimizados de produção, execute dentro de `frontend/`:

```bash
npm run build
```

O resultado é gravado em `frontend/dist/`. Em produção, sirva o frontend e
encaminhe `/api` à API no mesmo domínio, ou configure `VITE_API_BASE_URL` no
build para apontar ao endereço da API com CORS configurado no ambiente.

O Dashboard usa os endpoints de chamados e usuários existentes. Os indicadores,
gráficos e filtros são calculados sobre os registros retornados pela API dentro
do escopo permitido ao usuário. Administradores veem a visão geral e gerenciam
atribuições; técnicos acessam a fila disponível e seus chamados; solicitantes
acompanham os próprios chamados e podem abrir novos.

## Publicação online

O repositório inclui `netlify.toml` para publicar o frontend com base `frontend`,
comando `npm run build`, diretório `dist` e fallback SPA para `index.html`.
Configure no Netlify a variável de build `VITE_API_BASE_URL` com a origem HTTPS
da API (por exemplo, `https://sua-api.example.com`, sem `/api/v1`). O frontend
usa esse endereço para chamadas à API e para abrir sua documentação.

A API inclui um `Dockerfile` para hospedagem em um serviço que execute
containers, como Render. Use um PostgreSQL gerenciado e persistente; SQLite é
adequado para desenvolvimento e testes, não para o disco efêmero de um
container de produção. O backend aceita URLs PostgreSQL `postgres://` e
`postgresql://` e as adapta para o driver psycopg incluído nos requisitos.

Configure estas variáveis no serviço da API:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | URL privada de conexão fornecida pelo PostgreSQL gerenciado. |
| `JWT_SECRET_KEY` | Segredo aleatório com pelo menos 32 bytes. Gere e armazene no cofre de segredos do host; nunca use o exemplo de desenvolvimento nem o versionamento. |
| `CORS_ORIGINS` | Origens exatas do frontend, separadas por vírgula e sem caminhos, como `https://seu-site.netlify.app`. |
| `PORT` | Normalmente fornecida automaticamente pelo host do container. |

No Render, confirme que `DATABASE_URL` é a URL PostgreSQL interna do banco
criado na mesma região (não a URL pública/externa) e que
`JWT_SECRET_KEY` está definida. A aplicação falha explicitamente no startup se
essas configurações forem inválidas ou se o Render tentar usar SQLite.
`PORT` é injetada pelo Render; não é necessário fixar uma porta no painel.

As migrations são aplicadas quando a API inicia. Depois que o banco existir,
crie o administrador inicial executando `python -m app.bootstrap_admin
admin@example.com` em um terminal/one-off job seguro do serviço com acesso às
mesmas variáveis. Não habilite o cadastro público de administradores: o
cadastro web cria somente solicitantes.

Ordem recomendada: crie PostgreSQL e API, configure `JWT_SECRET_KEY` e
`DATABASE_URL`, publique o frontend, então defina `CORS_ORIGINS` com o domínio
real emitido pelo Netlify e `VITE_API_BASE_URL` com a URL real da API. Refaça o
deploy do frontend após mudar a variável `VITE_API_BASE_URL`; variáveis `VITE_`
são incorporadas durante o build. Valide `https://sua-api.example.com/health`,
cadastro, login e chamados nos domínios implantados. Não publique segredos em
issues, logs ou no repositório.

O token JWT é mantido somente na memória da aplicação e enviado como
`Authorization: Bearer`. Ele não é gravado em `localStorage` ou
`sessionStorage`; portanto, atualizar ou fechar a página encerra a sessão e
exige novo login. O backend não oferece refresh token. A API ainda não mantém
eventos de alteração de chamados, então os detalhes mostram a criação e a
última atualização disponíveis, não uma trilha histórica de status.

## Autenticação e autorização

Cadastre-se em `POST /api/v1/auth/register` e autentique-se em
`POST /api/v1/auth/login`. O cadastro público sempre cria um solicitante; não
é possível escolher um perfil privilegiado pelo endpoint público. Senhas têm
no mínimo 8 caracteres e são armazenadas com hash Argon2id.

O login retorna um token JWT com validade de 30 minutos. Envie-o nas rotas
protegidas pelo cabeçalho:

```http
Authorization: Bearer <token>
```

As rotas `/` e `/health` são públicas. Tokens inválidos, expirados ou de contas
desativadas resultam em HTTP `401`; usuário autenticado sem permissão recebe
HTTP `403`. O perfil atual é consultado no banco a cada requisição protegida.

### Perfis e permissões

| Perfil | Permissões |
|---|---|
| Solicitante (`requester`) | Abre chamados e lista ou consulta somente os próprios chamados. Não altera status. |
| Técnico (`technician`) | Consulta chamados disponíveis e os atribuídos a si, assume chamados disponíveis e atualiza o status dos chamados atribuídos a si. |
| Administrador (`admin`) | Consulta e gerencia chamados, inclusive registros históricos sem proprietário; gerencia perfis e ativações de usuários; atribui ou remove técnicos dos chamados. |

Todo chamado novo recebe automaticamente o usuário autenticado como
proprietário. Solicitantes não acessam chamados de terceiros. Chamados legados
sem proprietário não são exibidos a solicitantes ou técnicos; somente
administradores podem visualizá-los. A API valida essas permissões no servidor.

Administradores podem ativar, desativar e alterar o perfil dos usuários. Não
há exclusão definitiva de usuários, para preservar o histórico. Usuários
desativados não podem fazer login e seus tokens existentes deixam de autorizar
requisições. O sistema impede desativar ou rebaixar o último administrador
ativo.

## Endpoints disponíveis

| Método | Endpoint | Acesso e descrição |
|---|---|---|
| GET | `/` | Público; retorna informações do serviço. |
| GET | `/health` | Público; verifica a disponibilidade da API. |
| POST | `/api/v1/auth/register` | Público; cadastra um solicitante. |
| POST | `/api/v1/auth/login` | Público; autentica e retorna um token JWT. |
| GET | `/api/v1/users` | Administrador; lista usuários. |
| PATCH | `/api/v1/users/{user_id}/role` | Administrador; altera o perfil de usuário. |
| PATCH | `/api/v1/users/{user_id}/active` | Administrador; ativa ou desativa uma conta. |
| POST | `/api/v1/tickets` | Solicitante ou administrador; cria um chamado. |
| GET | `/api/v1/tickets` | Autenticado; lista chamados conforme o perfil. |
| GET | `/api/v1/tickets/available` | Técnico ou administrador; lista chamados disponíveis. |
| POST | `/api/v1/tickets/{ticket_id}/claim` | Técnico; assume um chamado disponível. |
| PATCH | `/api/v1/tickets/{ticket_id}/assignee` | Administrador; atribui ou remove a atribuição de um técnico. |
| GET | `/api/v1/tickets/{ticket_id}` | Autenticado; consulta um chamado conforme as permissões do perfil. |
| PATCH | `/api/v1/tickets/{ticket_id}/status` | Técnico atribuído ou administrador; atualiza o status. |

### Exemplo de login

Envie um JSON para `POST /api/v1/auth/login`:

```json
{
  "email": "usuario@example.com",
  "password": "uma-senha-segura"
}
```

### Exemplo de criação de chamado

Envie um JSON para `POST /api/v1/tickets` com um token de solicitante ou
administrador:

```json
{
  "title": "Computador sem acesso à internet",
  "description": "Estação de trabalho não consegue acessar sites.",
  "category": "rede",
  "priority": "alta"
}
```

## Testes automatizados

Com as dependências instaladas e o ambiente virtual ativado, execute a partir
da raiz do projeto:

```bash
pytest -v
```

Os testes utilizam SQLite em memória ou bancos temporários para cobrir
autenticação, permissões por perfil, operações administrativas simultâneas e
migrations de bancos legados, sem alterar o banco local de desenvolvimento.

## Estado do desenvolvimento

O SmartDesk AI está em evolução contínua. A implementação atual inclui
autenticação JWT, perfis de acesso, gestão de usuários, migrations e fluxo de
atendimento de chamados. Não há cobrança, assinaturas, preços, planos, limites
de uso ou recursos pagos implementados. A base multiempresa (`companies` e
`memberships`) pode apoiar futuramente planos por empresa; antes disso, será
necessário definir regras de plano e limites no backend e escolher/configurar
um provedor de pagamentos. Nenhum preço ou recurso futuro é oferecido como
disponível.

## Autor

Uanderson Martins — [GitHub](https://github.com/Uanderson777)
