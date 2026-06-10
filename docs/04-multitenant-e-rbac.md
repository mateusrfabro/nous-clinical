# 4. Multi-tenant & RBAC

> **Leia isto antes de criar/alterar qualquer rota.** É o coração da segurança
> do produto. Errar aqui vaza dado entre clínicas (ou entre médicos) — risco de
> negócio e de LGPD.

## Parte A — Isolamento multi-tenant

Cada **clínica** é um tenant. Toda entidade do domínio tem `clinica_id`. O
isolamento é **automático** — você normalmente **não** escreve `WHERE clinica_id`
à mão.

### O motor: `app/services/tenant.py`
`init_tenant(db)` (chamado no app factory) registra **dois listeners**:

1. **Leitura — `do_orm_execute`**: antes de cada `SELECT`, injeta
   `with_loader_criteria(Modelo, Modelo.clinica_id == g.clinica_id)` para cada
   entidade escopada. Ou seja: toda query das entidades abaixo já vem filtrada
   pela clínica atual, **sem o caller fazer nada**. Esquecer um filtro **não vaza**.

2. **Escrita — `before_flush`**: toda linha **nova** de uma entidade "dona" que
   esteja sem `clinica_id` recebe a clínica atual (ou, em contexto sem request —
   seed/job/teste single-tenant — a única clínica existente).

```python
escopados = [Paciente, Profissional, Agendamento, Atendimento,
             LancamentoFinanceiro, Procedimento, Exame, Convenio]
donos = escopados + [Usuario]   # recebem clinica_id na criação (Usuario não é escopado na leitura)
```

`Usuario` **não** é escopado na leitura (o login precisa achar o usuário antes de
saber a clínica). `Clinica` é o próprio tenant — não tem `clinica_id`.

### Quem é a "clínica atual"
`g.clinica_id`, populado no `before_request` `_set_clinica_atual`
(`app/__init__.py`) a partir de `current_user.clinica_id`. **Superadmin →
`g.clinica_id = None` → sem escopo** (vê todas as clínicas, de propósito). Rotas
**públicas** (sem login) também têm `g.clinica_id = None` → sem escopo (por isso o
portal público precisa filtrar manualmente, ver [doc 5](05-white-label.md)).

### ⚠️ A pegadinha do `session.get()` + identity map
`db.session.get(Modelo, id)` **a frio** (objeto não está na sessão) emite um
SELECT e **respeita** o escopo → cross-tenant retorna `None`. **MAS**, se o objeto
já está no identity map da sessão, `get()` devolve do cache **sem reaplicar** o
critério. Em produção isso não vaza (cada request tem sessão nova e nunca carregou
o objeto de outra clínica), mas:

- **Entidades sem `clinica_id` próprio** (`PrecoConvenio`) **não** são escopadas —
  protegidas por **guarda explícita**. Veja `procedimentos.excluir_preco`: compara
  `Procedimento.clinica_id` (o pai, esse sim escopado) com `clinica_atual()`.
- **`AuditLog`** (sem `clinica_id`) é escopado na tela `/auditoria` por
  `AuditLog.usuario_id IN (usuários da clínica)`.

### Como testar isolamento (padrão `expunge_all`)
No teste, criar a entidade da "clínica B" e dar `commit()` deixa o objeto no
identity map da sessão compartilhada do conftest → o request seguinte acertaria o
cache e o teste daria falso-positivo. Use `db.session.expunge_all()` após criar a
clínica B (força SELECT a frio = produção), e verifique com
`.execution_options(ignore_tenant=True)`:

```python
cb, ag = _clinica_b_com_agendamento()
db.session.expunge_all()                    # espelha produção (sem cache)
client_admin.post(f"/agenda/{ag.id}/status", data={"status": "confirmado"})
# verificação SEM escopo (g.clinica_id do request fica pendurado no app_context):
assert _sem_escopo(Agendamento, ag.id).status == "agendado"   # bloqueado
```
Exemplos reais: `tests/test_auditoria_pos.py`, `tests/test_multitenant.py`.

### `ignore_tenant`
Para um SELECT que **deve** cruzar tenants (ex.: superadmin, jobs, portal por
slug), use `.execution_options(ignore_tenant=True)` — o listener pula o escopo.
Use com consciência.

---

## Parte B — RBAC (papéis e permissões)

### Papéis (`Usuario.tipo`)
| Papel | Escopo | Acessa |
|---|---|---|
| **superadmin** | cross-tenant (sem clínica) | gerencia clínicas (`/clinicas`), painel consolidado. **Não** tem escopo. |
| **admin** | a clínica dele | tudo da clínica, **inclusive Relatórios, Auditoria e Aparência (white-label)**. |
| **profissional** | a clínica dele | a própria agenda, prontuário, e **Pacientes limitado aos seus** (com quem tem agendamento). |
| **recepcao** | a clínica dele | agenda, pacientes, financeiro, Cadastro de Itens/Convênios. **NÃO** vê prontuário (LGPD), **NÃO** vê Relatórios/Auditoria, **NÃO** vê/lança despesas de aluguel/salário/imposto. |

### Decorators (`app/auth_decorators.py`)
Sempre depois de `@login_required`:
```python
superadmin_required        # só superadmin
admin_required             # só admin
profissional_required      # profissional COM cadastro (check_cadastro=True)
recepcao_ou_admin          # recepção ou admin
clinico_required           # profissional (com cadastro) ou admin — prontuário/exames
equipe_required            # recepção + admin + profissional — tela de pacientes
```
> `clinico_required` usa `check_cadastro=True`: um `Usuario` tipo=profissional
> **sem** registro `Profissional` é barrado (senão o guard de "própria agenda",
> que depende de `current_user.profissional`, seria pulado).

### Matriz de permissões (`app/permissions.py`)
Fonte legível do "quem pode o quê" (PACIENTE_VER, FINANCEIRO_VER, RELATORIO_VER…).
Os **decorators continuam sendo o enforcement de rota**; a matriz alimenta o
global Jinja **`pode("financeiro:ver")`** pra mostrar/ocultar UI de forma
consistente com os gates. Mantenha os dois em sincronia.

### Escopos de papel ALÉM do decorator (cuidado)
Alguns controles são **dentro da view**, não no decorator:
- **Médico só vê os pacientes dele**: `pacientes.listar/detalhe` filtram por
  `_ids_pacientes_do_profissional()`. (decorator é `equipe_required`).
- **Médico só atende a própria agenda**: guard em `agenda.atendimento`
  (`ag.profissional_id == current_user.profissional.id`).
- **Recepção não vê/age em despesa sensível**: `financeiro._filtro_categoria()`
  esconde `aluguel/salario/imposto` nas listas/sums, e `pagar`/`cancelar`/`novo`
  bloqueiam (403) a recepção nessas categorias.

### Checklist ao criar/alterar uma rota
1. Tem `@login_required` + o `@<papel>_required` certo?
2. Busca por id de entidade escopada? O escopo automático cobre — mas confirme
   que a entidade **está** em `escopados`. Se **não** tiver `clinica_id` (ex.:
   PrecoConvenio), adicione **guarda explícita** pela posse.
3. POST? Tem CSRF (global do Flask-WTF) — exceto endpoints de máquina com token
   próprio (`/tarefas/lembretes`).
4. É rota pública? `g.clinica_id` é `None` → **sem escopo** → filtre por clínica
   manualmente (ex.: portal por slug).
5. Escreveu o teste negativo (cross-tenant / papel errado)?
