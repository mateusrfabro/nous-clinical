# 2. Setup & run

## Requisitos
- **Python 3.12** (caminho usado no projeto: `C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe`).
- Git. (Docker e Postgres só pra prod/integração.)

## Instalação (dev)
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

## Variáveis de ambiente (`.env`)
Copie `.env.example` → `.env`. **Nunca commite `.env`** (está no `.gitignore`).
Principais (ver `config.py`):

| Var | Para que | Obrigatória |
|---|---|---|
| `SECRET_KEY` | sessão/CSRF/tokens assinados | **sim em prod** (boot falha sem ela) |
| `DATABASE_URL` | Postgres em prod (dev usa SQLite `instance/nous.db`) | prod |
| `FLASK_ENV` | `development` (default) ou `production` | não |
| `PORT` | porta do dev server (default 5050) | não |
| `IDLE_SESSION_LIFETIME` | timeout de inatividade (seg) | não |
| `TAREFAS_TOKEN` | autentica o endpoint `/tarefas/lembretes` (cron) | se usar cron |
| `PUBLIC_BASE_URL` | base dos links públicos (confirmação/lembrete) | recomendável |
| SMTP_* / `TELEGRAM_*` | envio de e-mail / Telegram | opcional |
| `ANTHROPIC_API_KEY` | chave Claude (compartilhada pelo Suporte IA e Concierge IA) | opcional |
| `AJUDA_IA_ATIVA` | liga o modo IA do Suporte (default-OFF) | opcional |
| `CONCIERGE_ATIVO` | liga o modo IA do Concierge (mensagem de retorno; default-OFF → usa template grátis) | opcional |
| `CONTATO_COMERCIAL` | CTA da landing `/` (link WhatsApp/`mailto:`); vazio → "Entrar" | opcional |

## Banco: migrations
Sempre exporte `FLASK_APP=run.py` antes dos comandos `flask db`.
```bash
export FLASK_APP=run.py                     # Windows PS: $env:FLASK_APP="run.py"
python -m flask db upgrade                   # aplica até o head
python -m flask db migrate -m "descricao"    # gera migration a partir dos models
python -m flask db heads                      # mostra o head atual
```
> **SQLite + coluna NOT NULL nova:** adicione `server_default=...` na migration
> (senão "Cannot add a NOT NULL column with default value NULL"). Ex.:
> migration do campo `tema`.
> **FK em batch (SQLite):** dê nome à constraint (`name="fk_..."`) — SQLite em
> batch exige constraint nomeada.

## Seed (dados de demonstração)
```bash
python scripts/seed.py                  # 1 clínica, admin/recepção/2 profissionais, dados demo
python scripts/seed_demo_clinicas.py    # 3 clínicas isoladas p/ validar multi-tenant (senha 123demo)
```
Logins do seed padrão (senha `demo123`): `admin@nous.com`, `recepcao@nous.com`,
`dra.ana@nous.com`, `dr.bruno@nous.com`. Superadmin: `flask criar-superadmin`.

## Rodar
```bash
python run.py            # dev server na porta 5050 (debug). NUNCA em prod.
```
Prod usa **gunicorn** (ver `entrypoint.sh` / `docker-compose.yml`).

## Testes (a rede de segurança — rode sempre)
```bash
python -m pytest tests/ -q                       # suíte completa
python -m pytest tests/test_portal.py -q          # um arquivo
python -m pytest tests/ --cov=app --cov-report=term-missing   # cobertura
```
- Os testes usam **SQLite em arquivo temporário** + `db.create_all()` (não tocam o DB de dev) — ver `tests/conftest.py`. Por isso **mudança de modelo aparece nos testes sem migration**, mas a migration ainda é obrigatória pro dev/prod.
- Fixtures principais: `app`, `client`, `client_admin`, `client_recepcao`, `client_prof`.
- CSRF é desabilitado em `testing` (os testes postam sem token).

## Lint & segurança estática (mesmo do CI)
```bash
python -m ruff check app/ tests/      # lint
python -m bandit -r app/ -ll          # segurança estática
python -m pip_audit -r requirements.txt   # CVEs nas dependências
```
CI (`.github/workflows/ci.yml`): pytest + cobertura mínima 70% + ruff + bandit + pip-audit.

## CLI úteis (`app/commands.py`)
```bash
flask lembretes [--data YYYY-MM-DD]                 # dispara lembretes do dia (idempotente)
flask criar-superadmin --email X --senha Y --nome Z  # cria o superadmin da plataforma
```

## Comandos comuns (com o Python do projeto)
```bash
PY="C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe"
$PY -m pytest tests/ -q
$PY run.py
```
