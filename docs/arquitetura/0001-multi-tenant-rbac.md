# ADR 0001 — Multi-tenant, multi-unidade, RBAC granular, sessão e LGPD

- **Status:** Proposto
- **Data:** 2026-06-06
- **Autor:** Arquitetura (Nous Clinical)
- **Decisores:** Fundador + Sócio
- **Contexto de produto:** vamos vender Nous Clinical para várias clínicas em breve
  (multi-clínica é necessidade próxima), mas a **demo atual NÃO pode ser desestabilizada**.

> Documento escrito sobre o código real do repositório (`app/models.py`,
> `app/__init__.py`, `app/auth_decorators.py`, `config.py`, rotas em `app/routes/`,
> `tests/conftest.py`). Nomes de tabela/coluna citados são os que existem hoje.

---

## 1. Contexto e decisão

### 1.1 Onde estamos hoje (fatos do código)

- **Single-tenant físico.** Uma instância = uma clínica. Não existe nenhuma
  noção de "clínica" ou "tenant" no schema. Toda linha de `pacientes`,
  `agendamentos`, `atendimentos`, `lancamentos_financeiros` etc. pertence
  implicitamente à única clínica da instância.
- **Auth por sessão server-side.** `flask_login` com cookie de sessão assinado,
  `login_manager.session_protection = "strong"`, `PERMANENT_SESSION_LIFETIME =
  timedelta(hours=8)` (em `config.py`). O `load_user` faz
  `db.session.get(Usuario, int(user_id))`.
- **Papéis por enum string.** `Usuario.tipo ∈ {admin, profissional, recepcao}`.
  Gating por decorators em `app/auth_decorators.py` (`role_required`,
  `admin_required`, `recepcao_ou_admin`, `clinico_required`,
  `profissional_required`).
- **Isolamento "lógico" pontual já existe** mas é por *recurso*, não por tenant:
  em `agenda.py` o profissional só vê a própria agenda
  (`q.where(Agendamento.profissional_id == current_user.profissional.id)`), e
  em `atendimento()` há checagem IDOR manual
  (`ag.profissional_id != current_user.profissional.id`).
- **Padrões invioláveis (CLAUDE.md):** SQLAlchemy 2.0 (`select`/`db.session.get`,
  nunca `Model.query.get`), `Numeric(12,2)` para dinheiro, datas UTC no DB +
  filtros BR no display, CSP estrito (sem `onclick` inline), migrations Alembic
  com `render_as_batch=True` (essencial para SQLite/ALTER).

### 1.2 Decisão

1. **Adotar multi-tenant via shared-DB + coluna `clinica_id` (row-level
   isolation).** Justificativa detalhada em §2.
2. **Introduzir `unidades` (multi-unidade dentro de uma clínica) como segundo
   eixo de escopo,** mas apenas a partir da Fase 2 — multi-unidade é refinamento,
   multi-tenant é o que destrava vendas.
3. **Manter Flask-Login / sessão server-side. NÃO trocar por JWT agora.** (§1.3)
4. **Manter os papéis enum (`Usuario.tipo`) como estão na Fase 0/1 e introduzir
   RBAC tabelado só na Fase 3,** atrás de um façade de permissões que já pode ser
   usado pelas rotas desde já (§5). Evita reescrita big-bang dos decorators.
5. **Criptografia em repouso seletiva (CPF e prontuário), via `TypeDecorator`
   SQLAlchemy,** e não criptografia de banco inteiro nem por-tenant key
   management complexo nesta fase (§7).

### 1.3 O que explicitamente NÃO faremos agora (anti over-engineering)

O documento do sócio pede "JWT + AES-256 + RBAC granular + franquias/consolidado".
São coisas boas no lugar certo. No nosso estágio, várias delas são over-engineering
imediato. Sendo honesto:

| Pedido do doc | Decisão agora | Por quê |
|---|---|---|
| **Trocar sessão por JWT** | **Não.** Manter Flask-Login. | Este é um app **server-rendered** (Jinja), não SPA/API. JWT resolve auth *stateless cross-service / SPA / mobile*. Num monólito Flask com cookies, JWT só **piora** a segurança: token no `localStorage` = exposto a XSS; "logout remoto" e revogação exigem blacklist server-side, ou seja, você reinventa a sessão server-side que já tem de graça. Adotar JWT **apenas se/quando** houver uma API pública/SPA/app mobile separados — aí, escopo limitado a essa API, conviv­endo com a sessão do app web. |
| **AES-256 em tudo** | **Não.** Só CPF e prontuário (§7). | Criptografar colunas que você precisa filtrar/ordenar (nome, email de login, datas) quebra índices e busca, e dá falsa sensação de segurança se a chave vive ao lado do dado. Foco no que é "dado sensível" LGPD de verdade. |
| **RBAC tabelado já na Fase 0** | **Não.** Fase 3. | Três papéis fixos hoje cobrem 100% das rotas. Tabelar RBAC antes de ter um requisito real de papel customizado é complexidade sem retorno. Mas **preparamos o terreno** com um façade `pode(perm)` (§5) para a migração ser indolor. |
| **Schema-per-tenant / DB-per-tenant** | **Não.** Shared-DB. | §2 — custo operacional e de migração desproporcional ao estágio. |
| **Franquias / consolidado de rede** | **Fase 4, opcional.** | Depende de fechar clientes que sejam redes. Modelado para caber (clínica pode ter `rede_id`), mas não construído agora. |

**Princípio guia:** cada fase tem que deixar a demo verde (`pytest tests/ -q` 100%)
e o produto vendável. Nada de branch de 3 meses.

---

## 2. Modelo de isolamento escolhido

### 2.1 Comparação

| Critério | Shared-DB + `clinica_id` (row-level) | Schema-per-tenant | DB-per-tenant |
|---|---|---|---|
| Esforço de implementação | **Baixo** (add coluna + escopo) | Médio-alto (router de schema, search_path) | Alto (provisionamento, N conexões) |
| Custo operacional | **1 DB, 1 pool, 1 migration** | 1 DB, N schemas, migration × N schemas | N DBs, N pools, N backups |
| Migrations Alembic | **1 vez** | Loop por schema (tooling extra) | Loop por DB |
| Isolamento de dados | Lógico (risco: filtro esquecido) | Forte (search_path) | Mais forte (físico) |
| "Vazamento" por bug | Possível → exige enforcement defensivo (§4) | Improvável | Quase impossível |
| Relatórios cross-tenant (rede/consolidado) | **Trivial** (um `GROUP BY clinica_id`) | Difícil (UNION de schemas) | Muito difícil (cross-DB) |
| Onboarding de cliente novo | INSERT em `clinicas` | `CREATE SCHEMA` + migrate | provisionar DB |
| Custo por cliente em SQLite/Postgres pequeno | **~zero** | baixo | alto |
| LGPD "apagar tudo de um tenant" | `DELETE WHERE clinica_id=` | `DROP SCHEMA` (limpo) | `DROP DATABASE` (limpo) |
| Limite de escala | Tabelas grandes precisam de índice composto e, no extremo, particionamento | Bom até centenas de schemas | Bom para poucos tenants enormes |

### 2.2 Recomendação: **Shared-DB + `clinica_id`**

Para o estágio (poucas a dezenas de clínicas, todas pequenas/médias, Postgres
em prod via `docker-compose`), shared-DB é o ponto certo de custo/benefício:

- Uma migration, um pool, um backup. O `entrypoint.sh` e o CI não mudam de forma.
- Onboarding de clínica = `INSERT INTO clinicas`. Self-service trivial depois.
- O eixo de **rede/franquia/consolidado** que o sócio quer (Fase 4) fica *fácil*
  exatamente neste modelo: consolidado é `WHERE clinica_id IN (...)` ou
  `GROUP BY clinica_id`. Em schema/DB-per-tenant isso seria um inferno de UNION.
- O único ponto fraco — vazamento por filtro esquecido — é **mitigável de forma
  sistemática** com `with_loader_criteria` global (§4), não dependendo de
  disciplina humana em cada query.

Quando reavaliar: se algum cliente exigir isolamento físico por compliance
contratual, ou se uma tabela passar de dezenas de milhões de linhas e o
particionamento por `clinica_id` não bastar. Não é o caso hoje.

---

## 3. Mudanças de schema

### 3.1 Novas tabelas

```text
clinicas
  id            PK
  nome          String(150) NOT NULL
  slug          String(60)  UNIQUE NOT NULL   # subdomínio/identificador
  cnpj          String(18)  UNIQUE NULL
  ativo         Boolean NOT NULL default True
  rede_id       FK redes.id NULL              # reservado p/ Fase 4 (nullable desde já)
  criado_em     DateTime(tz)

unidades                                       # Fase 2
  id            PK
  clinica_id    FK clinicas.id NOT NULL  index
  nome          String(120) NOT NULL          # "Matriz", "Filial Centro"
  endereco/cidade/...                          # opcionais
  ativo         Boolean NOT NULL default True
  __table_args__ = UniqueConstraint(clinica_id, nome)

redes                                          # Fase 4 (opcional)
  id PK; nome String(150) NOT NULL; criado_em
```

Para RBAC tabelado (**Fase 3** — não antes):

```text
roles
  id PK
  clinica_id  FK clinicas.id NULL      # NULL = role de sistema (admin/recepcao/profissional)
  nome        String(50) NOT NULL      # ex.: "Financeiro Sênior"
  __table_args__ = UniqueConstraint(clinica_id, nome)

permissions
  id PK
  codigo      String(60) UNIQUE NOT NULL   # ex.: "PATIENT_CREATE"
  descricao   String(150)

role_permissions
  role_id        FK roles.id
  permission_id  FK permissions.id
  PK (role_id, permission_id)

user_roles
  usuario_id  FK usuarios.id
  role_id     FK roles.id
  PK (usuario_id, role_id)
```

> Nota: `permissions` é catálogo global (não tem `clinica_id`). `roles` é por
> clínica (clínica pode criar papéis próprios) + roles de sistema com
> `clinica_id NULL`. Isso evita duplicar o catálogo de permissões por tenant.

### 3.2 Colunas `clinica_id` (e, na Fase 2, `unidade_id`) por tabela existente

Todas as tabelas de **dados de negócio** ganham `clinica_id` (NOT NULL ao fim da
Fase 1). Tabelas que só fazem sentido dentro de uma clínica via FK pai *poderiam*
herdar o tenant por join, mas **denormalizar `clinica_id` direto em cada tabela é
a decisão** — simplifica o escopo global (§4) e índices, ao custo de uma coluna.

| Tabela (real) | `clinica_id` | `unidade_id` (Fase 2) | Observação |
|---|---|---|---|
| `usuarios` | **Sim** | não | Um usuário pertence a 1 clínica. (Se no futuro um médico atender 2 clínicas, vira N:N `usuario_clinicas` — fora de escopo.) |
| `profissionais` | **Sim** | sim (lotação) | |
| `pacientes` | **Sim** | sim (unidade de cadastro) | unique de `cpf` precisa virar composto (§3.3) |
| `agendamentos` | **Sim** | **sim** | unidade é onde a consulta ocorre |
| `atendimentos` | **Sim** | sim | dado sensível; tenant explícito reforça isolamento |
| `procedimentos` | **Sim** | não | catálogo por clínica |
| `precos_convenio` | **Sim** | não | tabela de preços por clínica |
| `itens_atendimento` | **Sim** (denormalizado) | não | herdaria via `atendimento`, mas denormaliza p/ escopo uniforme |
| `lancamentos_financeiros` | **Sim** | sim | financeiro por clínica/unidade |
| `exames` | **Sim** | não | dado sensível |
| `audit_logs` | **Sim** (nullable) | não | login_fail anônimo não tem clínica → nullable |

`redes` não tem `clinica_id` (é o nível acima). `permissions` é global.

### 3.3 Unique constraints que viram compostas com o tenant

Hoje são **globais** e quebram multi-tenant (clínica B não conseguiria cadastrar
um paciente com CPF que a clínica A já tem; dois admins de clínicas diferentes não
poderiam usar o mesmo email):

| Constraint hoje (em `app/models.py`) | Vira |
|---|---|
| `Paciente.cpf` — `unique=True` (linha `cpf = db.Column(db.String(14), unique=True)`) | `UniqueConstraint("clinica_id", "cpf", name="uq_paciente_clinica_cpf")` |
| `Usuario.email` — `unique=True, index=True` | **Decisão: manter email globalmente único** (login é por email puro, sem subdomínio no form atual). Alternativa se quiser reuso de email entre clínicas: `UniqueConstraint("clinica_id", "email")` + login que descobre a clínica pelo host/slug. Recomendo **manter global** na Fase 1 (menos atrito no fluxo de login existente em `auth.py`) e reavaliar só se um cliente reclamar. |
| `PrecoConvenio` — `UniqueConstraint("procedimento_id", "convenio")` | Já é seguro: `procedimento_id` já é por clínica. Opcional adicionar `clinica_id` por consistência de índice. |
| `Profissional.usuario_id` — `unique=True` | Permanece (1:1 usuário↔profissional dentro do tenant; usuário já é de 1 clínica). |
| `Atendimento.agendamento_id` — `unique=True` | Permanece (1:1, agendamento já é do tenant). |
| `LancamentoFinanceiro.agendamento_id` — `unique=True` | Permanece. |

### 3.4 Índices

Como **toda query passa a filtrar por `clinica_id`**, ele deve ser a **primeira
coluna** de índices compostos, casando com os filtros que já existem nas rotas:

| Índice | Casa com a query em |
|---|---|
| `ix_agendamentos_clinica_inicio (clinica_id, inicio)` | `agenda.listar` (`inicio >= ini, inicio < fim`) |
| `ix_agendamentos_clinica_prof_inicio (clinica_id, profissional_id, inicio)` | filtro por profissional + `_conflito_horario` |
| `ix_lancamentos_clinica_pagoem (clinica_id, status, pago_em)` | `financeiro.fluxo` (`status=pago, pago_em` no período) |
| `ix_lancamentos_clinica_status_tipo (clinica_id, status, tipo)` | `financeiro.contas` (pendentes por tipo) |
| `ix_pacientes_clinica_nome (clinica_id, nome_completo)` | listagens ordenadas por nome |
| `ix_atendimentos_clinica_paciente (clinica_id, paciente_id)` | histórico clínico |
| `ix_audit_clinica_criadoem (clinica_id, criado_em)` | auditoria por clínica |

Os índices simples atuais (`Agendamento.inicio`, `LancamentoFinanceiro.pago_em`
etc.) podem ser substituídos pelos compostos correspondentes.

---

## 4. Enforcement de isolamento (o ponto crítico)

O risco número 1 do shared-DB é **esquecer um `WHERE clinica_id = ...`** numa query
nova e vazar dados entre clínicas. Disciplina manual não escala. Estratégia em
três camadas, defensiva:

### 4.1 Tenant atual via sessão (fonte da verdade)

O `clinica_id` do usuário logado já está em `usuarios.clinica_id`. Guardamos na
sessão no login e expomos via um helper, **sem** depender de `current_user` em
todo lugar:

```python
# app/services/tenant.py  (novo, Fase 1)
from flask import g, has_request_context
from flask_login import current_user

def clinica_atual_id():
    if not has_request_context():
        return None
    cid = getattr(g, "_clinica_id", None)
    if cid is not None:
        return cid
    if current_user.is_authenticated:
        cid = current_user.clinica_id
        g._clinica_id = cid
        return cid
    return None
```

> Fonte = `current_user.clinica_id` (server-side, não confiável no cliente).
> **Nunca** aceitar `clinica_id` vindo de form/query/header do usuário.

### 4.2 Escopo automático global (defesa principal): `with_loader_criteria`

Em vez de confiar que cada rota lembre do filtro, instalamos um critério de
carregamento **global por request** que injeta `clinica_id = clinica_atual_id()`
em **toda** entidade marcada como tenant-scoped. SQLAlchemy 2.0 suporta isso via
um event listener `do_orm_execute` + `with_loader_criteria`:

```python
# app/services/tenant.py  (Fase 1)
from sqlalchemy import event, with_loader_criteria
from sqlalchemy.orm import Session
from app import db

class TenantMixin:
    """Marca entidades sujeitas a escopo automático por clinica_id."""
    pass  # classes herdam: class Paciente(TenantMixin, db.Model)

@event.listens_for(Session, "do_orm_execute")
def _tenant_scope(execute_state):
    if execute_state.is_select and not execute_state.execution_options.get("skip_tenant"):
        cid = clinica_atual_id()
        if cid is not None:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    TenantMixin,
                    lambda cls: cls.clinica_id == cid,
                    include_aliases=True,
                )
            )
```

Efeito: `db.session.execute(select(Agendamento)...)` e até
`db.session.get(Paciente, id)` passam a ser **automaticamente** escopados à
clínica do usuário. As rotas atuais (`agenda.py`, `financeiro.py`) **não precisam
mudar suas queries** — o `select(...)` que já existe ganha o filtro de tenant
"por baixo". Isso é o que torna a migração segura sem reescrever rotas.

- **Escape hatch** consciente: jobs/admin de plataforma que precisam cruzar
  tenants usam `.execution_options(skip_tenant=True)` explicitamente — fácil de
  auditar via grep.
- **Escrita (INSERT):** o escopo de leitura não preenche `clinica_id` em novos
  objetos. Para isso, ou (a) um `before_flush` que seta `clinica_id` em objetos
  novos `TenantMixin` sem clínica, ou (b) `default=clinica_atual_id` na coluna.
  Recomendo **(a) before_flush defensivo + (b) default** juntos (cinto e
  suspensório), e além disso um **assert no before_flush**: se um objeto
  tenant-scoped for inserido com `clinica_id` diferente do atual → `raise`.

### 4.3 Defesa em profundidade nas rotas sensíveis

O escopo global cobre `select`. Mas IDOR via `db.session.get` em **escrita**
(`mudar_status`, `pagar`, `cancelar` em `financeiro.py`/`agenda.py`) também fica
coberto porque `do_orm_execute` intercepta `get` também. Ainda assim:

- Manter as checagens de **recurso** existentes (profissional só a própria
  agenda) — são ortogonais ao tenant.
- Em rotas de plataforma (super-admin), tornar `skip_tenant` explícito e logar.

> **Risco residual honesto:** SQL bruto (`db.session.execute(text(...))`) e
> agregações com `func.sum` em colunas **não-entidade** podem escapar do
> `with_loader_criteria` (ele atua sobre entidades mapeadas). Hoje
> `financeiro._soma` faz `select(func.sum(LancamentoFinanceiro.valor))` — isso é
> sobre a entidade `LancamentoFinanceiro`, então **é coberto**. Mas qualquer
> agregação futura deve ser testada. Mitigação: um teste de "isolamento"
> (§9) que cria 2 clínicas e garante que nenhuma rota lista dados da outra.

---

## 5. RBAC granular

### 5.1 Papéis atuais → permissões do doc do sócio

Mapeamento dos 3 papéis para o vocabulário de permissões pedido:

| Permissão (código) | admin | recepcao | profissional |
|---|:---:|:---:|:---:|
| `PATIENT_VIEW` | ✓ | ✓ | ✓ |
| `PATIENT_CREATE` | ✓ | ✓ | – |
| `PATIENT_EDIT` | ✓ | ✓ | – |
| `AGENDA_VIEW` | ✓ | ✓ | ✓ (própria) |
| `AGENDA_CREATE` | ✓ | ✓ | – |
| `AGENDA_STATUS` | ✓ | ✓ | – |
| `RECORD_VIEW` (prontuário) | ✓ | – | ✓ (próprios) |
| `RECORD_WRITE` | ✓ | – | ✓ (próprios) |
| `EXAM_VIEW` / `EXAM_UPLOAD` | ✓ | – | ✓ |
| `FINANCE_VIEW` | ✓ | ✓ | – |
| `FINANCE_WRITE` | ✓ | ✓ | – |
| `REPORT_VIEW` / `REPORT_EXPORT` | ✓ | ✓* | – |
| `PROCEDURE_MANAGE` (catálogo/preços) | ✓ | – | – |
| `PROFESSIONAL_MANAGE` | ✓ | – | – |
| `USER_MANAGE` / `ROLE_MANAGE` | ✓ | – | – |
| `CLINIC_SETTINGS` | ✓ | – | – |

> Note que duas dimensões coexistem: a permissão ("pode ver agenda") e o escopo
> de recurso ("só a própria"). RBAC tabelado resolve a primeira; a segunda
> continua sendo regra de rota (`current_user.profissional.id`), como já é hoje.

### 5.2 Como evoluir `role_required` SEM quebrar rotas

Não trocar os decorators de uma vez. Introduzir um **façade de permissão** que,
na Fase 1, **deriva permissões dos papéis enum atuais** (tabela fixa em código), e
na Fase 3 passa a ler de `user_roles`/`role_permissions` — sem que as rotas mudem.

```python
# app/auth_decorators.py  (extensão, Fase 1 — coexiste com role_required)
PERMISSOES_POR_PAPEL = {
    "admin":        {"*"},                                  # tudo
    "recepcao":     {"PATIENT_*", "AGENDA_CREATE", "AGENDA_STATUS",
                     "FINANCE_*", "REPORT_VIEW", "AGENDA_VIEW", "PATIENT_VIEW"},
    "profissional": {"AGENDA_VIEW", "PATIENT_VIEW", "RECORD_*", "EXAM_*"},
}

def pode(perm: str) -> bool:
    # Fase 1: deriva do enum. Fase 3: troca corpo por consulta a user_roles.
    if not current_user.is_authenticated:
        return False
    concedidas = PERMISSOES_POR_PAPEL.get(current_user.tipo, set())
    return "*" in concedidas or perm in concedidas or _match_wildcard(perm, concedidas)

def permission_required(*perms):
    def decorator(f):
        @wraps(f)
        def decorated(*a, **k):
            if not all(pode(p) for p in perms):
                flash("Acesso restrito.", "error")
                return redirect(url_for("main.dashboard"))
            return f(*a, **k)
        return decorated
    return decorator
```

Estratégia de migração das rotas (incremental, opcional por rota):

- `@recepcao_ou_admin` → continua funcionando como está (não tocar).
- Rotas novas já usam `@permission_required("FINANCE_WRITE")`.
- Quando uma rota precisar de granularidade fina, trocar o decorator dela —
  uma de cada vez, com teste — sem big-bang.
- Em templates, `{% if pode('FINANCE_VIEW') %}` substitui checagens por `tipo`
  espalhadas (expor `pode` via `context_processor`, como já se faz com
  `whatsapp_url` em `__init__.py`).

Na **Fase 3**, o corpo de `pode()` passa a consultar `role_permissions` (com
cache por request em `g`), e `PERMISSOES_POR_PAPEL` vira o **seed** das roles de
sistema. As rotas e templates que já usam `pode()`/`permission_required` **não
mudam**. Esse é o motivo de introduzir o façade cedo.

---

## 6. Controle de sessão (equivalentes em Flask-Login)

O doc pede "timeout idle/absoluto, logout remoto, múltiplos dispositivos". Tudo
isso é **mais simples e mais seguro** com sessão server-side do que com JWT.

| Requisito | Implementação em Flask-Login/sessão |
|---|---|
| **Timeout absoluto** | Já existe: `PERMANENT_SESSION_LIFETIME = timedelta(hours=8)` + `session.permanent = True`. Ajustar valor por política. |
| **Timeout idle (inatividade)** | `before_request` que carimba `session["ultimo_acesso"]`; se `now - ultimo_acesso > IDLE_TTL` → `logout_user()`. ~15 linhas, sem libs. |
| **Logout remoto / revogar sessão** | Adicionar `usuarios.sessao_epoch` (int). No login, gravar o epoch atual na sessão (`session["epoch"]`). No `load_user`/`before_request`, se `session["epoch"] != user.sessao_epoch` → invalida. "Logout de todos os dispositivos" = `user.sessao_epoch += 1`. Forçar logout após troca de senha já encaixa aqui (há `senha_atualizada_em` no modelo). |
| **Múltiplos dispositivos** | Cookies de sessão já são independentes por device. Para *listar/encerrar* sessões individualmente, migrar de cookie-session para **server-side session store** (Flask-Session + Redis — já temos Redis no compose) e manter um registro `sessoes_ativas(usuario_id, session_id, ip, ua, ultimo_acesso)`. Opcional; só se o cliente pedir gestão de dispositivos. |
| **session-fixation** | Já mitigado: `session_protection = "strong"` + `login_user` regenera. |

Conclusão: **nenhum desses requisitos justifica JWT.** O único item que pede
infra extra (gestão granular de dispositivos) é melhor servido por Redis-backed
sessions, não por tokens.

---

## 7. LGPD / criptografia em repouso

### 7.1 O que merece criptografia (e o que não)

| Dado | Criptografar em repouso? | Racional |
|---|---|---|
| `pacientes.cpf` | **Sim** | Identificador sensível, alvo de vazamento, e **não** precisa ser ordenável. Para busca exata por CPF, manter um `cpf_hash` (HMAC-SHA256 com chave da app) indexado, e o valor cifrado à parte. |
| `atendimentos.queixa/evolucao/prescricao` | **Sim** | Prontuário = dado de saúde (LGPD art. 11). Texto livre, nunca filtrado em SQL → cifrar é barato. |
| `exames` (arquivo) | **Sim (no storage), opcional no DB** | O conteúdo já vive fora de `static/` com `arquivo_key` opaca. Cifrar o blob no storage (envelope) é o ganho real; a linha do DB só tem metadados. |
| `pacientes.telefone/email/endereço` | **Não agora** | PII, mas usados em busca/contato; cifrar quebra usabilidade. Proteger por controle de acesso + auditoria + TLS. Reavaliar. |
| `usuarios.email` | **Não** | É a credencial de login; precisa ser indexável/único. |
| Nome do paciente | **Não** | Buscado/ordenado em todas as listagens. Cifrar inviabiliza UX. |
| Dinheiro, datas, status | **Não** | Não são dados pessoais sensíveis; filtrados/agregados. |

> Honestidade: "AES-256 em tudo" soa seguro mas, com a chave na mesma app, contra
> o atacante realista (dump de DB) protege; contra app comprometida, não. O ganho
> concentra-se em CPF e prontuário. Cifrar nome/telefone/email custa busca e
> índices por proteção marginal. **Não** é o melhor uso do esforço agora.

### 7.2 Estratégia técnica: `TypeDecorator` (transparente ao ORM)

Criptografia **a nível de coluna**, transparente para as rotas (queixa/evolução
continuam sendo `str` no Python):

```python
# app/services/cripto.py  (Fase final / paralela)
from cryptography.fernet import Fernet      # AES-128-CBC + HMAC (autenticado)
from sqlalchemy.types import TypeDecorator, Text
from flask import current_app

class Cifrado(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):     # Python -> DB
        if value is None: return None
        return _fernet().encrypt(value.encode()).decode()
    def process_result_value(self, value, dialect):   # DB -> Python
        if value is None: return None
        return _fernet().decrypt(value.encode()).decode()
```

Uso no modelo: `queixa = db.Column(Cifrado)` — as rotas em `agenda.py` não mudam.

- **Chave:** `DATA_ENCRYPTION_KEY` em env (nunca commitada — CLAUDE.md), separada
  de `SECRET_KEY`. Em prod, idealmente vinda de um secrets manager (Vault/KMS),
  não do `.env`.
- **Rotação:** suportar `MultiFernet` (lista de chaves) para reencrypt sem
  downtime. Fora de escopo das primeiras fases.
- **Por-tenant key:** over-engineering agora. Uma chave da aplicação basta para o
  modelo de ameaça (dump de DB). Reavaliar se um cliente exigir BYOK.
- **CPF buscável:** coluna `cpf` vira `Cifrado` + nova `cpf_hash`
  (`HMAC(chave, cpf_normalizado)`) com índice único composto
  `(clinica_id, cpf_hash)`. Busca por CPF = busca pelo hash.

> Migração de dados existentes: re-escrever as linhas (ler→cifrar→gravar) num
> script idempotente, fora do horário de demo. Em SQLite dev, trivial; em
> Postgres prod, em lote.

---

## 8. Plano de migração faseado (não quebra a demo)

Princípios: cada fase é um PR pequeno; migrations com `render_as_batch=True`
(já ligado em `__init__.py`, necessário para SQLite ALTER); testes verdes ao fim
de cada fase. Datas em UTC, dinheiro `Numeric(12,2)` (inalterado).

### Fase 0 — Tenant existe, mas é invisível (sem escopo ainda)

**Objetivo:** introduzir o conceito sem mudar comportamento.

1. Migration: criar tabela `clinicas`; inserir **1 clínica default** (id=1,
   slug `nous`, nome da clínica da demo) no próprio `upgrade()` (data migration).
2. Migration: add coluna `clinica_id` **NULLABLE** em todas as tabelas da §3.2,
   sem FK NOT NULL ainda.
3. Migration (backfill): `UPDATE <tabela> SET clinica_id = 1 WHERE clinica_id IS NULL`.
4. Modelo: adicionar `clinica_id = db.Column(..., db.ForeignKey("clinicas.id"))`
   nullable + relationships. **Ainda sem** `with_loader_criteria`.
5. Seed (`scripts/seed.py`) e `conftest._seed_minimo`: criar a clínica e setar
   `clinica_id` nos objetos do seed.

> Comportamento idêntico ao de hoje (uma clínica). Testes existentes passam
> intactos, pois nada filtra por tenant ainda.

### Fase 1 — Escopo automático + NOT NULL + façade de permissão

1. Modelo: `Usuario.clinica_id` populado; `clinica_atual_id()` + listener
   `do_orm_execute` (§4.2) + `TenantMixin` nas entidades tenant-scoped.
2. Login (`auth.py`): gravar `session["clinica_id"]` no `login_user` (defesa) e
   continuar derivando de `current_user.clinica_id` como fonte.
3. `before_flush` que seta/valida `clinica_id` em objetos novos (§4.2).
4. Migration: tornar `clinica_id` **NOT NULL** (após backfill garantido) e criar
   índices compostos da §3.4; trocar `Paciente.cpf` unique global por
   `UniqueConstraint(clinica_id, cpf)`.
5. Introduzir `pode()`/`permission_required` + `context_processor` (§5.2),
   derivando do enum. **Não** trocar decorators existentes ainda.
6. Teste de isolamento (§9): 2 clínicas, garantir não-vazamento.

> A demo (clínica 1) continua funcionando. Rotas não mudam suas queries — o
> escopo entra por baixo. Risco controlado por teste de isolamento.

### Fase 2 — Multi-unidade

1. Migration: tabela `unidades` + `unidade_id` (nullable→backfill→define
   política) em `agendamentos`, `lancamentos_financeiros`, `profissionais`,
   `pacientes`, `atendimentos`.
2. Seletor de unidade no header (server-side, em `g`/sessão), análogo ao tenant.
3. Filtros de agenda/financeiro ganham dimensão "unidade" (opcional na UI).

> Unidade é refinamento; clínicas sem múltiplas unidades veem "Unidade única"
> (default), sem mudança de UX.

### Fase 3 — RBAC tabelado

1. Migration: `roles`, `permissions`, `role_permissions`, `user_roles`.
2. Seed: roles de sistema (`admin`/`recepcao`/`profissional`) + catálogo de
   permissões a partir de `PERMISSOES_POR_PAPEL`; popular `user_roles` a partir
   de `Usuario.tipo` (data migration).
3. Trocar **apenas o corpo** de `pode()` para consultar `user_roles`
   (com cache por request). Assinatura e callers inalterados.
4. UI de gestão de papéis (admin) — nova, atrás de `ROLE_MANAGE`.
5. `Usuario.tipo` permanece como "papel primário" para compat/relatórios (não
   remover ainda; depreciar depois).

### Fase 4 — Redes / consolidado (opcional, sob demanda)

1. Migration: `redes` + `clinicas.rede_id`.
2. Relatórios consolidados: `GROUP BY clinica_id` com `skip_tenant` explícito +
   um papel `REDE_VIEW`. Trivial no shared-DB (era o ponto forte de §2).

### Manter os testes verdes em cada fase

- Fase 0: nenhum teste quebra (nada filtra).
- Fase 1: `conftest` precisa de clínica (próxima seção); ajustes mecânicos.
- Cada fase: rodar `python -m pytest tests/ -q` antes de abrir PR (CI exige 70%
  de cobertura — manter ou subir).

---

## 9. Impacto nos testes

### 9.1 `tests/conftest.py`

- `_seed_minimo()` precisa **criar uma `Clinica`** antes de tudo e setar
  `clinica_id` em `Usuario`, `Profissional`, `Paciente`, `Agendamento`.
  Sugestão: fixture/helper `clinica_a` (id padrão) + `clinica_b` para testes de
  isolamento.
- O login de teste (`_login`) já injeta `_user_id` na sessão; como
  `clinica_atual_id()` deriva de `current_user.clinica_id`, **não** precisa setar
  `clinica_id` na sessão manualmente — mas pode-se setar para robustez.
- Substituir o `Usuario.query.filter_by(...)` em `_login` por
  `db.session.execute(select(Usuario)...)` (alinhar ao padrão 2.0; opcional, mas
  o `with_loader_criteria` global ignora `.query` legado de forma menos previsível
  — bom momento para limpar).
- Novo helper de fixture para criar dados numa clínica específica
  (`criar_paciente(clinica)`), para os testes de isolamento.

### 9.2 Testes que quebram (e por quê)

| Teste/área | Por que quebra | Correção |
|---|---|---|
| Qualquer teste que cria `Paciente`/`Agendamento`/`Lancamento` direto no DB | A partir da Fase 1, `clinica_id` é NOT NULL | `before_flush` seta default OU o helper passa `clinica_id` |
| Testes de unicidade de CPF | `cpf` deixa de ser unique global | Ajustar expectativa (unique agora é por clínica) |
| `test_auth_perfil.py` (novo, untracked) e fluxos de login | Se passar a depender de `clinica_id` na sessão | Garantir seed com clínica |
| Testes de agenda/financeiro que executam `select(...)` sem usuário logado | Sem `current_user`, `clinica_atual_id()` retorna `None` → escopo desligado; mas testes que assumem "vê tudo" logados verão só a clínica do user | Geralmente OK (1 clínica no seed); revisar os que criam dados cross |

> Estimativa: a maior parte das quebras é **mecânica** (seed precisa de clínica).
> O trabalho real de teste é o **novo** teste de isolamento (criar clínica B,
> logar como user da A, garantir que nenhuma rota — agenda, financeiro, pacientes,
> relatórios — retorna dados da B). Esse teste é a rede de segurança do §4.

---

## 10. Riscos, mitigações e esforço

### 10.1 Riscos e mitigações

| Risco | Sev. | Mitigação |
|---|---|---|
| **Vazamento entre tenants** (filtro esquecido / SQL bruto / agregação fora de entidade) | **Alta** | `with_loader_criteria` global (§4.2) cobre `select`/`get`; teste de isolamento automatizado em CI; proibir `text()` sem `skip_tenant` revisado; revisar agregações `func.*`. |
| Escrita com `clinica_id` errado (IDOR de criação) | Alta | `before_flush` valida `clinica_id == clinica_atual_id()` e dá `raise` em divergência; nunca aceitar `clinica_id` do cliente. |
| Migration NOT NULL falha por linha órfã | Média | Backfill obrigatório (Fase 0) + verificação `SELECT count(*) WHERE clinica_id IS NULL = 0` antes do ALTER. |
| `render_as_batch` em SQLite recriando tabela e perdendo dado/constraint | Média | Já ligado; testar `upgrade`+`downgrade` em SQLite e Postgres no CI antes de prod. |
| `with_loader_criteria` impactar performance/eager loads | Média | Índices compostos com `clinica_id` à frente (§3.4); medir queries das telas quentes (agenda/fluxo). |
| Quebra de unicidade de email entre clínicas | Baixa | Decisão de manter email global na Fase 1 (sem atrito no login atual); reavaliar. |
| Cripto de coluna quebrar busca por CPF | Média | `cpf_hash` HMAC indexado + valor cifrado à parte (§7.2). |
| Sessão Redis (gestão de dispositivos) virar dependência dura | Baixa | Só na Fase opcional; Redis já existe no compose. |
| Demo desestabilizada por big-bang | **Alta** | Faseamento Fase 0→4, cada fase com testes verdes; `clinica_id` nullable antes de NOT NULL. |

### 10.2 Estimativa de esforço (dev sênior, ordem de grandeza)

| Fase | Escopo | Esforço |
|---|---|---|
| **Fase 0** | `clinicas` + `clinica_id` nullable + backfill + seed/conftest | **2–3 dias** |
| **Fase 1** | Escopo global + NOT NULL + índices + unique composto + façade `pode()` + teste de isolamento | **5–8 dias** (núcleo de risco — caprichar nos testes) |
| **Fase 2** | Multi-unidade (schema + UI de seletor + filtros) | **4–6 dias** |
| **Fase 3** | RBAC tabelado + seed de roles + UI de gestão | **5–8 dias** |
| **Fase 4** | Redes/consolidado (opcional, sob demanda) | **3–5 dias** |
| **Cripto** (paralela) | `TypeDecorator` CPF/prontuário + `cpf_hash` + migração de dados | **3–5 dias** |
| **Sessão** (incremental) | Idle timeout + logout remoto (`sessao_epoch`) | **1–2 dias** |

**Caminho mínimo para "vendável a múltiplas clínicas":** Fase 0 + Fase 1
(~7–11 dias). O resto é incremental e sob demanda.

---

## Apêndice — Resumo das decisões

- Isolamento: **shared-DB + `clinica_id`** (row-level), com escopo automático via
  `with_loader_criteria`.
- Auth: **manter Flask-Login / sessão server-side**; JWT só para futura API/SPA.
- RBAC: **enum agora + façade `pode()`**; tabelar na Fase 3 sem mexer nas rotas.
- Cripto: **só CPF (cifrado + `cpf_hash`) e prontuário**, via `TypeDecorator`.
- Faseamento: **0 (tenant invisível) → 1 (escopo + NOT NULL) → 2 (unidade) →
  3 (RBAC) → 4 (redes)**, cada fase com a demo verde.
