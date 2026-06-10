# 7. Convenções & como adicionar uma feature

## Padrões invioláveis
- **NUNCA** `Model.query.get(id)` — use `db.session.get(Model, id)` (SQLAlchemy 2.0).
- **NUNCA** `from app.models import X` dentro de função (UnboundLocalError) — importe no topo.
- **NUNCA** `Float` pra dinheiro — sempre `Numeric(12, 2)` / `Decimal`.
- **NUNCA** `onclick=`/`on*=` inline nem `style=` inline (CSP bloqueia) — JS externo em `app/static/js/`, estilo dinâmico via classe ou `el.style.setProperty`.
- **NUNCA** commitar `.env` ou credenciais (só `.env.example` é versionado).
- **Datas:** DB em UTC (`DateTime(timezone=True)`); display via filtros `data_br`/`datetime_br`/`hora_br`; **cálculo de "hoje" em fuso BR** (`datetime.now(ZoneInfo("America/Sao_Paulo")).date()`, não `date.today()` — o container roda em UTC).
- **Prontuário (Atendimento) e Exame** são dados sensíveis LGPD — só profissional (dono) / admin.

## Estilo de código
- Python: 4 espaços, segue **ruff** (rode `ruff check app/ tests/`). Comentários e nomes em PT-BR, como o resto do código.
- Templates: sem lógica de negócio; respeite os tokens CSS e componentes existentes (`.card`, `.kpi-grid`, `.table` + `.table-wrapper`, `.btn*`, `.tag*`, `.toolbar` p/ filtros, `.flex-form` p/ pares de campos). Referencie arquivos como `path:linha`.
- Tabelas largas (≥5 colunas): envolva em `<div class="table-wrapper">` (scroll no mobile).

## Commits
Granulares, convenção: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
Trabalhe em branch (não na `master`). Rode a suíte **antes** de commitar.

## Passo a passo: adicionar uma feature
1. **Afeta o modelo?** Edite `app/models.py` →
   `flask db migrate -m "..."` → revise a migration (server_default em coluna
   NOT NULL nova; FK nomeada no SQLite) → `flask db upgrade`.
   - Entidade nova do domínio? Adicione em `escopados`/`donos` em
     `app/services/tenant.py` (senão **não** é isolada por clínica).
2. **Afeta rota?** No blueprint certo:
   - `@login_required` + o `@<papel>_required` correto ([doc 4](04-multitenant-e-rbac.md)).
   - Pense **IDOR**: busca por id de entidade escopada está coberta pelo escopo
     automático? Entidade sem `clinica_id` → guarda explícita pela posse.
   - POST tem CSRF (global). Rota pública → `g.clinica_id` é None → filtre manualmente.
3. **Afeta template?** Sem `style=`/`on*=` inline. Estilo dinâmico → classe ou JS
   CSSOM. Reuse os componentes do design system.
4. **Auditoria/sensível?** Chame `audit(AuditLog.ACAO_...)` nas ações relevantes
   (sem PII em `detalhes`).
5. **Teste** — escreva o caminho feliz **e** os negativos (papel errado,
   cross-tenant com `expunge_all`, validação). `pytest tests/ -q` 100% verde.
6. **Lint/segurança:** `ruff check`, e idealmente `bandit -r app/ -ll`.
7. **Commit** granular + atualize a doc (`CLAUDE.md` e/ou `docs/`).

## Onde as coisas moram (cola rápida)
| Preciso de… | Vá em |
|---|---|
| Nova entidade/coluna | `app/models.py` + migration + `tenant.py` (escopo) |
| Nova tela/endpoint | `app/routes/<blueprint>.py` + `app/templates/...` |
| Novo papel/permissão | `app/auth_decorators.py` + `app/permissions.py` |
| Cor/contraste/favicon | `app/services/cores.py` |
| Filtro/format Jinja, CSP, context | `app/__init__.py` |
| Lógica sem HTTP | `app/services/` |
| Estilo | `app/static/css/style.css` (1 arquivo, tokens em `:root`) |
| JS (sempre CSP-safe) | `app/static/js/` + incluir em `base.html` |

## Armadilhas conhecidas (não repita)
- `session.get()` pode devolver do **identity map** sem reaplicar o escopo — em
  teste use `expunge_all()` (ver [doc 4](04-multitenant-e-rbac.md)).
- `date.today()` num container UTC erra o dia à noite (fuso BR) — use a data BR.
- Reagendar consulta deve resetar `lembrete_enviado_em` (senão não reenvia lembrete).
- CSP quebra silenciosamente estilo/JS inline — se "não aplicou", confira se não é inline.
- SQLite: coluna NOT NULL nova precisa `server_default`; FK em batch precisa nome.
