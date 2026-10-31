# SmartDesk AI — frontend

Interface React + TypeScript, Vite e Tailwind CSS criada de forma independente em `frontend/`. O backend FastAPI, as migrations e o banco existentes não foram modificados. Não foi configurado nem executado deploy de produção.

## Executar localmente

Requer Node.js 22.12+ ou 24+ e uma API FastAPI já disponível em ambiente de desenvolvimento autorizado.

```bash
cd frontend
npm ci
npm run dev
```

Abra o endereço local informado pelo Vite. Por padrão, as requisições usam `/api/v1` na mesma origem. O proxy de desenvolvimento encaminha `/api` para `http://127.0.0.1:8000`, mantendo o caminho completo. O frontend não inicia o Python, não executa migrations e não cria banco. Não aponte uma revisão ou testes manuais de escrita para dados de produção.

Para usar outro servidor em desenvolvimento, configure `API_PROXY_TARGET` no ambiente do processo Vite. Essa configuração existe somente no servidor de desenvolvimento. `VITE_API_BASE_URL` permite escolher uma URL pública alternativa para a API, incluindo `/api/v1`; variáveis `VITE_*` são públicas no navegador e nunca devem receber segredos. Não inclua credenciais em URLs.

Para publicação futura, falta conectar a URL real do backend a um proxy HTTPS na mesma origem. O proxy do Vite não existe no site estático publicado. Acesso direto a uma API em outro domínio depende de CORS no backend, que permanece inalterado. Não foi adicionado `netlify.toml`, alterada a configuração do site ou definido um backend fictício. Depois de configurar a hospedagem e revisar a integração, os artefatos do frontend podem ser gerados em `frontend/dist`; esta etapa não executou build nem deploy.

## Testes

```bash
npm test
npm run typecheck
```

Os testes de componentes usam Vitest, Testing Library e jsdom, com respostas simuladas para `request`. Os testes do cliente HTTP simulam `fetch`. Eles não enviam requisições ao FastAPI nem alteram contas, senhas, chamados ou banco. Os dados e identificadores de sessão dos testes são sintéticos.

A cobertura inclui cadastro, login inválido, ações de cada perfil, criação e detalhes de chamados, busca e filtros, paginação, assumir chamados, conflito de atribuição, alteração de status, administração de perfil e ativação, proteção do último administrador, atribuição e remoção de técnico, registros históricos, mudança de perfil, logout, respostas HTTP inválidas e erros de rede.

## Funcionalidades e contratos

| Fluxo | Endpoint existente |
|---|---|
| Cadastro de solicitante | `POST /api/v1/auth/register` |
| Login | `POST /api/v1/auth/login` |
| Listagem paginada e criação | `GET`, `POST /api/v1/tickets` |
| Detalhes | `GET /api/v1/tickets/{id}` |
| Fila disponível | `GET /api/v1/tickets/available` |
| Assumir chamado | `POST /api/v1/tickets/{id}/claim` |
| Status | `PATCH /api/v1/tickets/{id}/status` |
| Atribuição administrativa | `PATCH /api/v1/tickets/{id}/assignee` |
| Usuários paginados | `GET /api/v1/users` |
| Perfil e ativação | `PATCH /api/v1/users/{id}/role`, `PATCH /api/v1/users/{id}/active` |

Solicitantes abrem e acompanham chamados sem controles de status. Técnicos acessam a fila, assumem chamados disponíveis e atualizam apenas os atribuídos a si. Administradores gerenciam chamados, atribuições e usuários. A API continua sendo a autoridade de acesso; ocultar um botão não concede nem revoga permissões.

Como não existe `/me` e o login não retorna perfil, o cliente consulta `/users?limit=1`; um sucesso identifica administrador. Somente em caso de 403, consulta `/tickets/available?limit=1`; sucesso identifica técnico. Se ambas negarem acesso com 403, confirma autenticação em `/tickets?limit=1` para identificar solicitante. Falhas de rede, 401 e 5xx não são tratadas como perfil. A detecção é repetida ao navegar ou atualizar dados, permitindo refletir mudanças de perfil. Essa compatibilidade exige requisições adicionais, sem novos endpoints.

O JWT permanece apenas em memória na aba, sem armazenamento em cookies, localStorage ou sessionStorage. Recarregar a página exige novo login. Metadados `sub` e `exp` são lidos somente para ajustar a interface e expirar a sessão; a validação criptográfica e a autorização continuam no FastAPI. Respostas 401 de rotas protegidas encerram a sessão. Erros 403, 409 e de validação aparecem na interface, sem registrar respostas de autenticação ou entradas sensíveis.

O dashboard resume exclusivamente os 20 registros da página atual, conforme indicado na tela. Busca e filtro também são locais à página; não representam estatísticas globais nem uma pesquisa completa no banco. Não há dados de demonstração no aplicativo. A área de atribuição usa o número do técnico, consultável em Usuários, e a API valida se ele está ativo. O acompanhamento mostra o estado atual e a última atualização: a API não fornece uma linha do tempo de eventos.

A interface adapta navegação, formulários e painéis a telas pequenas; tabelas possuem rolagem horizontal. Campos têm rótulos, botões de ícone têm nomes acessíveis, erros são anunciados e animações respeitam movimento reduzido. As fontes Google Fonts são opcionais e têm fallback local.

## Arquivos para revisão

`src/App.tsx` contém as telas e fluxos; `src/api.ts`, o cliente HTTP e descoberta de perfil; `src/types.ts`, os contratos; `src/styles.css`, o tema responsivo e Tailwind; `tests/`, os testes isolados. As configurações de Vite e TypeScript, o HTML de entrada, os scripts npm, o lockfile e o `.gitignore` são próprios desta pasta.

A verificação local também foi executada em Chromium, com respostas HTTP simuladas interceptadas no navegador: a página inicial retornou HTTP 200, os fluxos de solicitante, técnico e administrador funcionaram, e a largura móvel de 390 px não apresentou rolagem horizontal na página. As tabelas mantêm sua própria rolagem. Não houve erros de execução no navegador. Os 25 testes automatizados e a verificação de tipos passaram.

A integração real com um backend hospedado e o teste público completo permanecem pendentes da próxima etapa. Testes simulados e acesso local não demonstram que a aplicação já está publicada.
