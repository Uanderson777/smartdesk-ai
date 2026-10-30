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
- PyJWT
- pwdlib com Argon2id
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

Instale as dependências:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure uma chave JWT com pelo menos 32 bytes e inicie a API.

Windows (PowerShell):

```powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
uvicorn app.main:app --reload
```

Linux/macOS:

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uvicorn app.main:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. A documentação interativa
do FastAPI está em `http://127.0.0.1:8000/docs`.

## Endpoints disponíveis

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/` | Retorna informações do serviço. |
| GET | `/health` | Verifica a disponibilidade da API. |
| POST | `/api/v1/auth/register` | Cadastra um usuário. |
| POST | `/api/v1/auth/login` | Autentica o usuário e retorna um token JWT. |
| POST | `/api/v1/tickets` | Cria um chamado (requer autenticação Bearer). |
| GET | `/api/v1/tickets` | Lista chamados (requer autenticação; aceita `skip` e `limit`). |
| GET | `/api/v1/tickets/{ticket_id}` | Busca um chamado por ID (requer autenticação). |
| PATCH | `/api/v1/tickets/{ticket_id}/status` | Atualiza o status (requer autenticação). |

Cadastro e login recebem JSON. As senhas precisam ter pelo menos 8 caracteres;
elas são armazenadas com hash Argon2id. Para chamar as rotas de chamados, envie
o token retornado no login no cabeçalho `Authorization: Bearer <token>`.

Exemplo de login:

```json
{
  "email": "usuario@example.com",
  "password": "uma-senha-segura"
}
```

O segredo `JWT_SECRET_KEY` deve ser mantido fora do repositório e configurado
em cada ambiente. Tokens de acesso expiram após 30 minutos.

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
