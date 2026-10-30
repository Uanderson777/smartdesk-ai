# SmartDesk AI

Sistema inteligente de Service Desk desenvolvido com Python e FastAPI.

O projeto oferece uma API REST para abertura, consulta e atualização de chamados.
Está em evolução contínua; este README descreve somente o que está implementado
atualmente.

## Tecnologias

- Python 3.13
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite
- Pytest

## Requisitos

- Python 3.13
- Git

## Instalação e execução

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

Instale as dependências e inicie a API:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. A documentação interativa
do FastAPI está em `http://127.0.0.1:8000/docs`.

## Endpoints disponíveis

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/` | Retorna informações do serviço. |
| GET | `/health` | Verifica a disponibilidade da API. |
| POST | `/api/v1/tickets` | Cria um chamado. |
| GET | `/api/v1/tickets` | Lista chamados; aceita `skip` e `limit` para paginação. |
| GET | `/api/v1/tickets/{ticket_id}` | Busca um chamado pelo identificador. |
| PATCH | `/api/v1/tickets/{ticket_id}/status` | Atualiza o status de um chamado. |

### Exemplo de criação de chamado

Envie para `POST /api/v1/tickets`:

```json
{
  "title": "Computador sem acesso à internet",
  "description": "Estação de trabalho não consegue acessar sites.",
  "category": "rede",
  "priority": "alta"
}
```

## Testes automatizados

Execute a suíte a partir da raiz do projeto:

```bash
pytest -v
```

Os testes utilizam SQLite em memória, sem alterar o banco de desenvolvimento.

Último resultado registrado da suíte:

- 8 testes aprovados
- 0 falhas
- 1 aviso de depreciação relacionado à integração entre `httpx` e
  `starlette.testclient`

## Estado do desenvolvimento

O SmartDesk AI está em evolução contínua. A implementação atual cobre os
endpoints de chamados listados acima; funcionalidades futuras, como autenticação,
gestão de técnicos e recursos de inteligência artificial, ainda não estão
implementadas.

## Autor

Uanderson Martins — [GitHub](https://github.com/Uanderson777)
