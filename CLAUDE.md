# medsaas — guia do Claude Code

## O que é o projeto
SaaS de **gestão de clínica**: recepção marca consultas, profissionais de saúde
registram o atendimento (prontuário), gestor acompanha a operação. Nicho médico.

> **Nome `medsaas` é placeholder.** Trocar pela marca real depois (bindings em
> `config.py`, `docker-compose.yml`, `entrypoint.sh`, templates, CSS tokens).

**Origem:** scaffold de plataforma copiado do projeto Aggron (central de compras),
com o domínio de compras removido e substituído pelo domínio clínica/agenda.
**Stack:** Flask + SQLAlchemy + Alembic + Jinja2 + CSS vanilla + JS vanilla CSP-safe.

## 3 papéis do sistema (`Usuario.tipo`)
1. **admin** — dono/gestor. Acessa tudo (agenda, pacientes, profissionais, prontuário).
2. **profissional** — médico/profissional de saúde. Vê a própria agenda e registra
   atendimento clínico (prontuário) dos próprios pacientes. Vinculado a `Profissional`.
3. **recepcao** — recepcionista. Marca consultas e gerencia cadastro de pacientes,
   mas **NÃO** acessa prontuário (dado sensível LGPD).

## Modelos (`app/models.py`)
- **Usuario** — auth (email, senha Argon2id, tipo, ativo, telegram_chat_id).
- **Profissional** — 1:1 com Usuario(tipo=profissional): especialidade, conselho, cor de agenda.
- **Paciente** — cadastro (nome, CPF, nascimento, contato, convênio, observações).
- **Agendamento** — paciente + profissional + início/fim + status + valor/convênio.
- **Atendimento** — prontuário (queixa/evolução/prescrição). **Dado sensível LGPD.**
- **AuditLog** — trilha de auditoria (constantes `ACAO_*`).

## Fluxo principal
```
1. Admin cadastra profissionais (cria o login junto)        /profissionais/novo
2. Recepção/admin cadastra pacientes                        /pacientes/novo
3. Recepção/admin agenda consulta                           /agenda/novo
4. No dia: recepção muda status (confirmado/faltou)         /agenda/<id>/status
5. Profissional registra atendimento (prontuário)           /agenda/<id>/atendimento
   -> consulta vira status=atendido automaticamente
```
Status do agendamento: `agendado → confirmado → atendido` (ou `cancelado` / `faltou`).

## Ambiente
- **Python 3.12:** `C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe`
- **Rodar Flask:** `python run.py` (porta 5050; setar `PORT` se ocupada)
- **DB dev:** SQLite em `instance/medsaas.db`
- **Testes:** `python -m pytest tests/ -q`
- **Migration:** `flask db migrate -m "..."` + `flask db upgrade` (precisa `FLASK_APP=run.py`)
- **Seed:** `python scripts/seed.py`

## Logins de teste (após seed — senha `demo123`)
| Papel | Email |
|---|---|
| Admin | admin@medsaas.com |
| Recepção | recepcao@medsaas.com |
| Profissional | dra.ana@medsaas.com / dr.bruno@medsaas.com |

## Plataforma herdada (reaproveitada do Aggron)
- App factory + Talisman (CSP sem unsafe-inline) + CSRF + Flask-Limiter + Cache.
- Auth: login/logout/esqueci-senha/redefinir-senha, Argon2id + rehash-on-login,
  anti timing-attack, anti open-redirect, anti session-fixation, token de reset 1-uso.
- Services: `passwords`, `storage` (uploads), `email` (SMTP), `audit`, `pii`,
  `notificacoes` (e-mail + Telegram), `app_info` (versão/migration no /health).
- Error handlers 400/403/404/429/500 com template próprio.
- Design system CSS dark (tokens `--brand-*`, utilitários, componentes) — **paleta
  recolorida pra clínica (azul/teal); é placeholder, re-skin quando houver marca.**
- JS CSP-safe: `confirm-submit`, `form-submitting`, `data-bind`, `money-mask`.
- CI (`.github/workflows/ci.yml`): pytest+coverage 70% + ruff + bandit + pip-audit.
- Docker: `Dockerfile` + `docker-compose.yml` (Postgres + Redis + gunicorn) + `entrypoint.sh`.

## Padrões invioláveis (herdados)
- **NUNCA** `Model.query.get(id)` — usar `db.session.get(Model, id)` (SQLA 2.0).
- **NUNCA** import `from app.models import X` dentro de função (UnboundLocalError).
- **NUNCA** Float pra dinheiro — sempre `Numeric(12, 2)`.
- **NUNCA** `onclick=` inline (CSP bloqueia) — JS externo em `app/static/js/`.
- **NUNCA** commitar `.env` ou credenciais.
- Datas: DB em UTC (`DateTime(timezone=True)`), display via filtros `data_br`/`datetime_br`/`hora_br` (fuso Brasília).
- Prontuário (Atendimento) é dado sensível LGPD — só profissional/admin acessam.

## Durante implementação
1. Afeta modelo? → migration Alembic (`flask db migrate` + `upgrade`).
2. Afeta rota? → pensar IDOR (profissional só vê a própria agenda) + CSRF + decorator de papel.
3. Afeta template? → respeitar tokens CSS, sem style inline (CSP).
4. Escrever/atualizar teste → `pytest tests/ -q` 100%.
5. Commit granular: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.

## Backlog sugerido (próximos passos)
- Bloquear conflito de horário (mesmo profissional, mesmo slot).
- Visão de agenda semanal/calendário (hoje é lista por dia).
- Lembrete de consulta automático (Telegram/e-mail/WhatsApp).
- Registro de cadastro público de paciente (auto-agendamento online).
- Relatórios: faturamento por convênio, taxa de faltas, ocupação por profissional.
- Anexos de exames no Atendimento (storage já suporta upload).
- Re-skin com identidade visual real (criar skill de brand como no Aggron).