# medsaas

SaaS de **gestão de clínica** — agenda, pacientes e prontuário. Flask + SQLAlchemy +
PostgreSQL, com plataforma de segurança/auth/CI reaproveitada de um projeto irmão.

> `medsaas` é um nome placeholder — troque pela marca real quando definir.

## Rodar localmente (dev)

```bash
# 1. Python 3.12 + dependências
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 2. Variáveis mínimas
export FLASK_APP=run.py
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")

# 3. Banco (SQLite em dev) + dados de demonstração
flask db upgrade
python scripts/seed.py

# 4. Subir
python run.py            # http://127.0.0.1:5050
```

Logins de teste (senha `demo123`): `admin@medsaas.com`, `recepcao@medsaas.com`,
`dra.ana@medsaas.com`, `dr.bruno@medsaas.com`.

## Testes

```bash
python -m pytest tests/ -q
```

## Produção (Docker)

```bash
cp .env.example .env        # preencha SECRET_KEY e DB_PASSWORD
docker network create server_net
docker compose up -d --build
```

Postgres + Redis + gunicorn. Migrations e seed (se `RUN_SEED=true`) rodam no
`entrypoint.sh`. Healthcheck em `GET /health`.

## Arquitetura

```
app/
  __init__.py        # app factory, segurança (Talisman/CSP/CSRF/limiter), filtros Jinja
  models.py          # Usuario, Profissional, Paciente, Agendamento, Atendimento, AuditLog
  auth_decorators.py # role_required (admin / profissional / recepcao)
  routes/            # auth, main, pacientes, agenda, profissionais, perfil
  services/          # passwords (Argon2), storage, email, audit, pii, notificacoes, app_info
  static/css|js      # design system + JS CSP-safe
  templates/         # Jinja2 por domínio
migrations/          # Alembic (+ _idempotent.py helpers)
tests/               # pytest (smoke + autorização por papel)
scripts/seed.py      # dados de demonstração
```

Veja `CLAUDE.md` para o guia completo de domínio e padrões.