# Nous Clinical — guia do Claude Code

## O que é o projeto
**Nous Clinical** — *"Menos gestão. Mais medicina."* SaaS de **gestão de clínica** com
inteligência clínica: recepção marca consultas, profissionais de saúde registram o
atendimento (prontuário), gestor acompanha a operação e o financeiro. Nicho médico.
*Nous* (grego: inteligência/razão) — "a inteligência que auxilia a prática clínica".

> **Marca definida: Nous Clinical** (identidade dark indigo/teal). O scaffold nasceu
> como `medsaas` (placeholder) e foi rebatizado; bindings em `config.py`,
> `docker-compose.yml`, `entrypoint.sh`, templates e tokens CSS (`--brand-*`).

**Origem:** scaffold de plataforma copiado do projeto Aggron (central de compras),
com o domínio de compras removido e substituído pelo domínio clínica/agenda.
**Stack:** Flask + SQLAlchemy + Alembic + Jinja2 + CSS vanilla + JS vanilla CSP-safe.

## Papéis do sistema (`Usuario.tipo`) — multi-tenant por `clinica_id`
1. **superadmin** — plataforma, cross-tenant (sem `clinica_id`). Gerencia clínicas
   (`/clinicas`) e vê painel consolidado (totais cross-clínica). Não tem escopo.
2. **admin** — dono/gestor da clínica. Acessa tudo da clínica, **inclusive Relatórios
   e Auditoria** (`/auditoria`).
3. **profissional** — médico. Vê a própria agenda, registra prontuário e **acessa a
   tela de Pacientes limitada aos seus** (pacientes com quem tem agendamento).
4. **recepcao** — recepcionista. Agenda, pacientes, financeiro e **Cadastro de Itens/
   Convênios**. **NÃO** acessa prontuário (LGPD), **NÃO** vê Relatórios/Auditoria, e
   **NÃO** vê/lança despesas de aluguel/salário/imposto no financeiro.

> RBAC: decorators em `app/auth_decorators.py` (`superadmin_required`, `admin_required`,
> `recepcao_ou_admin`, `clinico_required`, `equipe_required`=recepção+admin+profissional).
> Matriz legível em `app/permissions.py` + global Jinja `pode(...)`.

## Modelos (`app/models.py`)
- **Clinica** — tenant. Escopo automático via `app/services/tenant.py`.
- **Usuario** — auth (email, senha Argon2id, tipo, ativo, telegram_chat_id, clinica_id).
- **Profissional** — 1:1 com Usuario(tipo=profissional): especialidade, conselho, cor,
  `duracao_padrao_min`, `comissao_percent`, **`sala`**.
- **Paciente** — cadastro (nome/CPF/nascimento **obrigatórios no form**, contato, endereço
  via CEP, convênio, observações).
- **Agendamento** — paciente + profissional + início/fim + status + valor/convênio + **sala**
  (puxada do profissional) + checkin_em. Duração selecionável (30/60/90/120).
- **Atendimento** — prontuário (queixa/evolução/prescrição). **Dado sensível LGPD.**
- **LancamentoFinanceiro** — receita/despesa (categoria, valor, status, forma, vencimento,
  pago_em). Liga opcional a paciente e a agendamento (1:1).
- **Procedimento/PrecoConvenio/ItemAtendimento** — itens faturáveis + preço por convênio.
- **Convenio** — cadastro centralizado de convênios (master data, por clínica). Datalist
  global `#convenios` injetado em `base.html` via `convenios_ativos()`.
- **AuditLog** — trilha de auditoria (constantes `ACAO_*`). Tela admin em `/auditoria`.

## Fluxo principal
```
1. Admin cadastra profissionais (cria o login junto)        /profissionais/novo
2. Recepção/admin cadastra pacientes                        /pacientes/novo
3. Recepção/admin agenda consulta                           /agenda/novo
4. No dia: recepção muda status (confirmado/faltou)         /agenda/<id>/status
5. Profissional registra atendimento (prontuário)           /agenda/<id>/atendimento
   -> consulta vira status=atendido automaticamente
6. Recepção/admin registra recebimento da consulta          /financeiro (botão "Receber" na agenda)
   -> cria LancamentoFinanceiro receita ligado ao agendamento
```
Status do agendamento: `agendado → confirmado → atendido` (ou `cancelado` / `faltou`).
Financeiro: fluxo de caixa (`/financeiro`), contas a receber/pagar (`/financeiro/contas`),
histórico financeiro no detalhe do paciente. Gate `recepcao_ou_admin` (profissional não vê).

## Ambiente
- **Python 3.12:** `C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe`
- **Rodar Flask:** `python run.py` (porta 5050; setar `PORT` se ocupada)
- **DB dev:** SQLite em `instance/nous.db`
- **Testes:** `python -m pytest tests/ -q`
- **Migration:** `flask db migrate -m "..."` + `flask db upgrade` (precisa `FLASK_APP=run.py`)
- **Seed:** `python scripts/seed.py`

## Logins de teste (após seed — senha `demo123`)
| Papel | Email |
|---|---|
| Admin | admin@nous.com |
| Recepção | recepcao@nous.com |
| Profissional | dra.ana@nous.com / dr.bruno@nous.com |

## Plataforma herdada (reaproveitada do Aggron)
- App factory + Talisman (CSP sem unsafe-inline) + CSRF + Flask-Limiter + Cache.
- Auth: login/logout/esqueci-senha/redefinir-senha, Argon2id + rehash-on-login,
  anti timing-attack, anti open-redirect, anti session-fixation, token de reset 1-uso.
- Services: `passwords`, `storage` (uploads), `email` (SMTP), `audit`, `pii`,
  `notificacoes` (e-mail + Telegram), `app_info` (versão/migration no /health).
- Error handlers 400/403/404/429/500 com template próprio.
- Design system CSS **tema claro** (tokens `--brand-*`/semânticos, utilitários, componentes) —
  **identidade oficial Nous Clinical: teal `#43B8A5` (primária/CTA) + sage `#6FB59C`
  (símbolo/2ª) + lilás `#B7A7F5` (accent) + navy `#1E293B` (ink/blocos escuros: auth,
  texto) + off-white `#F8FAF8`/`#EDF2F1` (fundo). Texto em fills de cor = navy
  (`--text-on-ouro`); texto sobre navy = claro (`--text-on-brand`/`--brand-cinza-claro`).
  Fonts Sora/Poppins/Inter. Logo = símbolo de rede (círculo + nós) + wordmark "Nous / CLINICAL".**
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

## Roadmap (doc de visão: Fase 1 MVP → Fase 2 CRM/IA → Fase 3 Concierge)
**Fase 1 (MVP) — feito:** Agenda, Pacientes, Atendimento, **Financeiro** (fluxo de caixa,
contas a receber/pagar, recebimento integrado, histórico financeiro do paciente).

Próximos passos sugeridos:
- **CRM Retorno (Fase 2, diferencial):** campo "retorno recomendado" (30/90/180/anual) no
  Atendimento + painel de retornos pendentes + lembretes automáticos.
- **Concierge IA (Fase 3):** geração de mensagens de acompanhamento (Claude API), busca de
  laboratórios/farmácias por convênio, sugestão de horários.
- Bloquear conflito de horário (mesmo profissional, mesmo slot).
- Visão de agenda semanal/calendário (hoje é lista por dia).
- Lembrete de consulta automático (Telegram/e-mail/WhatsApp).
- Registro de cadastro público de paciente (auto-agendamento online).
- Relatórios/BI: faturamento por convênio, taxa de faltas, ocupação por profissional.
- Anexos de exames no Atendimento (storage já suporta upload).
- Tema claro (re-theme do design system dark atual).