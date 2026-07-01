# 1. Arquitetura & visão geral

## O que é
**Nous Clinical** — *"Menos gestão. Mais cuidado."* SaaS **multi-tenant** de
gestão de clínica: recepção marca consultas, profissionais registram o
atendimento (prontuário), gestor acompanha operação e financeiro, e a plataforma
(superadmin) gerencia várias clínicas. Cada clínica é um **tenant** isolado.

## Stack
- **Flask 3** (app factory) + **SQLAlchemy 2.0** + **Alembic** (via Flask-Migrate)
- **Jinja2** (templates) + **CSS vanilla** (1 arquivo de design system) + **JS vanilla CSP-safe**
- **Flask-Login** (sessão), **Flask-WTF** (CSRF), **Flask-Limiter** (rate limit), **Flask-Caching**
- **Flask-Talisman** (CSP estrita, headers de segurança)
- Senhas **Argon2id** (`argon2-cffi`)
- Dev: SQLite (`instance/nous.db`). Prod: Postgres. Storage de arquivos local (trocável p/ S3).

## App factory (`app/__init__.py`)
`create_app(config_name)` faz, nesta ordem:
1. Carrega `config[config_name]` (de `config.py`).
2. `ProxyFix` (só prod) — confia em `X-Forwarded-*` atrás do proxy/Cloudflare.
3. Inicializa extensões: `db`, `login_manager`, `csrf`, `migrate`, `limiter`, `cache`.
4. **`init_tenant(db)`** — registra os listeners do escopo multi-tenant (ver [doc 4](04-multitenant-e-rbac.md)).
5. **Talisman** com a **CSP** (sem `unsafe-inline`; ver abaixo).
6. `init_storage(app)` — storage de uploads.
7. `before_request`: timeout de sessão por inatividade + **`_set_clinica_atual`** (popula `g.clinica_id`).
8. Registra os **16 blueprints**.
9. Error handlers (400/403/404/413/429/500) + filtro que **redige tokens** dos logs de acesso.
10. **Context processor** + **filtros Jinja** (datas BR, `brl`, status, white-label).

## Blueprints (`app/routes/`)
Um arquivo por blueprint. Todos os `register_blueprint` estão em `app/__init__.py`.

| Blueprint | Prefixo | Responsabilidade | Gate principal |
|---|---|---|---|
| `auth` | `/` | login/logout/recuperação de senha | público |
| `main` | `/` · `/produto` | landing comercial (`/` e alias `/produto`), dashboard, busca, tarefa de lembretes | misto |
| `pacientes` | `/pacientes` | CRUD de pacientes, busca CEP | equipe |
| `agenda` | `/agenda` | agenda (dia/semana), atendimento (prontuário), agendamento online | misto |
| `profissionais` | `/profissionais` | cadastro de profissionais (cria o login junto) | admin |
| `financeiro` | `/financeiro` | fluxo de caixa, contas, recebimento | recepção/admin |
| `crm` | `/crm` | painel de retornos/aniversariantes (recall) + Concierge (`/crm/mensagem-ia`) | recepção/admin |
| `procedimentos` | `/procedimentos` | "Cadastro de Itens" (itens faturáveis + convênios) | recepção/admin |
| `relatorios` | `/relatorios` | BI sob demanda + export CSV | admin |
| `exames` | `/exames` | anexos de exame (LGPD) | clínico |
| `documentos` | `/documentos` | PDFs de receita/atestado (reportlab) | clínico |
| `perfil` | `/perfil` | perfil do usuário, troca de senha | logado |
| `clinicas` | `/clinicas` | gestão de tenants (cria clínica + admin) | superadmin |
| `auditoria` | `/auditoria` | visualização da trilha de auditoria | admin |
| `configuracoes` | `/configuracoes` | white-label: tema/cor/logo/slug/QR/favicon | admin |
| `portal` | `/c/<slug>` | portal público POR clínica (login + agendamento com marca) | público |

## Services (`app/services/`) — lógica sem HTTP
- **`tenant.py`** — motor multi-tenant (escopo automático + atribuição de `clinica_id`). **Crítico.**
- **`audit.py`** — grava `AuditLog` (best-effort, captura IP/UA).
- **`storage.py`** — abstração de arquivos (local hoje; interface p/ S3).
- **`cores.py`** — luminância/contraste WCAG, CSS por cor, favicon SVG, cor de marca por tema.
- **`documentos_pdf.py`** — PDFs A4 de receita/atestado (reportlab); logo da clínica ou wordmark Nous.
- **`passwords.py`** — Argon2id (hash, verify, rehash-on-login, dummy anti-timing).
- **`tokens.py`** — tokens assinados (itsdangerous) p/ confirmação pública de consulta.
- **`lembretes.py`** — job de lembretes (WhatsApp template → e-mail → sem-canal), idempotente.
- **`concierge.py`** — gera a mensagem de retorno/reativação (template custo-zero por padrão; modo IA opcional via `CONCIERGE_ATIVO`). Não lê prontuário.
- **`ofx.py`** — parser de extrato OFX 1.x (SGML) / 2.x (XML), sem dependência externa.
- **`extrato.py`** — dispatcher OFX/CSV (CSV tolerante: delimitador, núm/data BR, `fitid` por hash).
- **`conciliacao.py`** — importa o extrato como `MovimentoBancario` e sugere o lançamento a casar.
- **`notificacoes.py`** / **`email.py`** — envio (SMTP + Telegram).
- **`pii.py`** — mascaramento de PII pra logs.
- **`app_info.py`** — versão + head de migration (exposto no boot e no `/health`).

## CSP (Content Security Policy) — inegociável
Definida em `app/__init__.py` (`csp = {...}`). **Sem `unsafe-inline`**:
- `script-src 'self'` → **nenhum `<script>` inline nem `onclick=`**. JS só em `app/static/js/`.
- `style-src 'self' fonts.googleapis.com` → **nenhum `style=` inline nem `<style>`**. Estilos dinâmicos via classe CSS ou `el.style.setProperty` no JS (CSSOM é permitido).
- `img-src 'self' data:`, `connect-src` herda `default-src 'self'` → fetch só same-origin.

Consequência prática: precisa de cor/posição dinâmica? Use `data-*` no HTML + JS
externo que aplica via `style.setProperty`. Exemplos: `agenda-week.js`,
`tema-cor.js`, `tema-preview.js`.

## Ciclo de um request autenticado
```
request
 → before_request: timeout de inatividade (LGPD)
 → before_request: _set_clinica_atual  ->  g.clinica_id = current_user.clinica_id
                                            (superadmin = None = sem escopo)
 → view (blueprint): @login_required + @<papel>_required
 → query ORM  ->  listener do_orm_execute injeta  WHERE clinica_id = g.clinica_id
                   automaticamente nas entidades escopadas
 → render template: context processor injeta white-label (tema/logo/cor/favicon)
 → response
```
O **escopo automático** é o coração da segurança multi-tenant — leia a [doc 4](04-multitenant-e-rbac.md).
