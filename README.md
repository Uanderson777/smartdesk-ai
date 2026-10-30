# SmartDesk AI

Sistema de Service Desk desenvolvido com Python e FastAPI, com evolução planejada para incluir uma base de conhecimento inteligente e recursos de IA.

> Projeto de portfólio em desenvolvimento. Esta primeira versão entrega uma API REST para abertura, consulta e atualização de chamados.

## Funcionalidades da versão inicial

- API REST documentada automaticamente com Swagger UI.
- Abertura de chamados com título, descrição, categoria e prioridade.
- Listagem e consulta de chamados por identificador.
- Atualização do status do chamado.
- Persistência local com SQLite para facilitar a execução inicial.
- Testes automatizados com Pytest.

## Tecnologias

- Python 3.13+
- FastAPI
- SQLAlchemy 2
- Pydantic
- SQLite
- Pytest

## Executar localmente

### 1. Clonar o repositório

```bash
git clone https://github.com/Uanderson777/smartdesk-ai.git
cd smartdesk-ai
```

### 2. Criar e ativar o ambiente virtual

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

### 3. Instalar dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Iniciar a API

```bash
uvicorn app.main:app --reload
```

Acesse:

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

## Executar os testes

```bash
pytest -v
```

## Endpoints iniciais

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Verifica a saúde da API |
| POST | `/api/v1/tickets` | Abre um chamado |
| GET | `/api/v1/tickets` | Lista chamados |
| GET | `/api/v1/tickets/{ticket_id}` | Consulta um chamado |
| PATCH | `/api/v1/tickets/{ticket_id}/status` | Atualiza o status |

## Exemplo de abertura de chamado

```json
{
  "title": "Computador sem acesso à internet",
  "description": "Estação de trabalho não consegue acessar sites.",
  "category": "rede",
  "priority": "alta"
}
```

## Roadmap

- [x] Estrutura inicial da API e documentação
- [ ] Autenticação JWT e controle de acesso por perfil
- [ ] Banco PostgreSQL e migrations com Alembic
- [ ] Gestão de técnicos e atribuição de chamados
- [ ] Histórico de alterações e métricas
- [ ] Base de conhecimento
- [ ] Busca semântica e sugestões com IA/RAG
- [ ] Docker e integração contínua com GitHub Actions

## Status

Em desenvolvimento. As funcionalidades marcadas como pendentes ainda não estão implementadas.

## Autor

Uanderson Martins — [GitHub](https://github.com/Uanderson777)
