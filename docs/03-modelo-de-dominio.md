# 3. Modelo de domínio

Todas as entidades estão em [`app/models.py`](../app/models.py). Convenções
invioláveis (ver [doc 7](07-convencoes.md)): dinheiro **sempre `Numeric(12,2)`**
(nunca Float); datas **`DateTime(timezone=True)` em UTC** (display via filtros BR).

## Diagrama textual
```
Clinica (TENANT) 1───* Usuario
   │                      │ 1:1 (tipo=profissional)
   │                      ▼
   ├── 1───* Profissional ── * Agendamento *── Paciente
   │            │                  │ 1:1            │
   │            │                  ▼                ├── * Atendimento ── * ItemAtendimento
   │            │             Atendimento           │        │ * Exame (LGPD)
   │            │                  │ 1:1            │
   ├── 1───* LancamentoFinanceiro ─┘ (recebimento)  └── financeiro/agendamentos
   ├── 1───* Procedimento ── * PrecoConvenio
   ├── 1───* Convenio        (master data)
   ├── 1───1 WhatsAppConta   (Cloud API; token cifrado)
   │         WhatsAppContato *── Paciente (match por telefone)
   │            └── 1───* WhatsAppMensagem (in/out)
   └── (AuditLog ligado por Usuario)
```

## Entidades

### `Clinica` — o tenant
Uma clínica/consultório. **Tudo do domínio carrega `clinica_id` apontando pra cá.**
Campos de white-label: `slug` (identificador público único), `tema`, `cor_primaria`,
`logo_key`/`logo_mime`, `ativo`. Escopo automático em `services/tenant.py`.

### `Usuario` — autenticação
`email` (único), `senha_hash` (Argon2id), `tipo` (papel), `ativo`, `clinica_id`
(**nullable**: o superadmin não pertence a clínica), `telegram_chat_id`.
Propriedades: `is_superadmin/is_admin/is_profissional/is_recepcao`.
`tipo ∈ {superadmin, admin, profissional, recepcao}` — ver [doc 4](04-multitenant-e-rbac.md).

### `Profissional` — 1:1 com Usuario(tipo=profissional)
`especialidade`, `registro_conselho`, `cor_agenda`, `duracao_padrao_min`,
`comissao_percent` (repasse), **`sala`** (puxada pra agenda). Criado junto com o
login em `profissionais.novo`.

### `Paciente`
`nome_completo`, `cpf` (único, **obrigatório no form**), `data_nascimento`
(obrigatório no form), contato, endereço (preenchível via CEP), `convenio`,
`observacoes`, `ativo`. CPF validado por dígitos verificadores.

### `Agendamento`
`paciente` + `profissional` + `inicio`/`fim` (UTC) + `status` + `valor`/`convenio`
+ **`sala`** + `checkin_em` + `lembrete_enviado_em`. Duração selecionável
(30/60/90/120). Status: `agendado → confirmado → atendido` (ou `cancelado`/`faltou`).
**`atendido` só é setado pelo registro do prontuário**, nunca manualmente.

### `Atendimento` — prontuário (DADO SENSÍVEL LGPD)
`queixa`/`evolucao`/`prescricao`, `retorno_em` (CRM recall), **`atestado_dias`/
`atestado_cid`** (atestado médico), 1:1 com Agendamento. Acesso só por
**profissional (o dono) ou admin**. Tem `itens` (ItemAtendimento) e `exames`.
`total_itens` soma os itens em Decimal. Edição registra `ACAO_ATENDIMENTO_EDITADO`
na auditoria. Exporta **receita** e **atestado** em PDF (`app/routes/documentos.py`
+ `app/services/documentos_pdf.py`, reportlab A4 — logo da clínica ou wordmark Nous).

> **Anexar exame sem perder o rascunho:** o prontuário e o upload de exame ficam no
> **mesmo `<form>`** (`enctype=multipart`); o botão "Anexar" usa `formaction` p/
> `exames.upload`, que **persiste o rascunho** (helper `aplicar_campos_prontuario`)
> antes de salvar o arquivo — sem marcar a consulta como atendida. Corrige o bug em
> que anexar apagava queixa/evolução/prescrição (viravam "none").

### `Procedimento` / `PrecoConvenio` / `ItemAtendimento`
Catálogo de itens faturáveis ("Cadastro de Itens"). `Procedimento.valor_padrao`;
`PrecoConvenio` dá preço por convênio (**não tem `clinica_id` próprio** — posse
via Procedimento pai); `ItemAtendimento` é o snapshot do item consumido num
atendimento (preserva o valor histórico).

### `Convenio` — master data
Cadastro centralizado de convênios por clínica (evita texto livre duplicado).
Datalist global `#convenios` em `base.html` via `convenios_ativos()`.

### `LancamentoFinanceiro` — receita ou despesa
`tipo` (receita/despesa), `categoria`, `valor` (**Numeric**), `status`
(pendente/pago/cancelado), `forma_pagamento`, `vencimento`, `pago_em`. Liga
opcional a `paciente` e a `agendamento` (1:1 **unique** → recebimento idempotente).
`vencido` compara em **data BR**.

### `Exame` — anexo (LGPD)
Arquivo no `storage` (fora de `static/`), só `arquivo_key` opaca no DB.
Download por rota autenticada com checagem de posse (`clinico_required`).

### `WhatsAppConta` / `WhatsAppContato` / `WhatsAppMensagem` — WhatsApp Business (Cloud API)
Integração multi-tenant com o WhatsApp Business da Meta. **Inerte por padrão**: só
há tráfego/custo quando `WHATSAPP_ATIVO` (global) está on **E** a conta está
`ativo=True` com token. Detalhe da integração (webhook, custos, onboarding) em
[doc 10](10-whatsapp-integracao.md).

- **`WhatsAppConta`** — 1:1 com Clínica (`UniqueConstraint` em `clinica_id`). Guarda
  os IDs da Meta: `phone_number_id` (**único global** — roteia o webhook de volta pra
  clínica dona), `waba_id`, `display_phone`, `nome_exibicao`. O access token é
  **SEGREDO**: guardado **cifrado** (`token_cifrado`, Fernet — `services/cripto.py`)
  e nunca exibido/logado. `configurada` = tem número + token.
- **`WhatsAppContato`** — uma "thread" da inbox = a outra ponta da conversa. `wa_id`
  (número internacional só dígitos), `nome` (push name da Meta), `nao_lidas`,
  `ultima_em`. Ligado **opcionalmente** a um `Paciente` (casado por telefone) pra dar
  contexto clínico. `UniqueConstraint(clinica_id, wa_id)`.
- **`WhatsAppMensagem`** — uma mensagem da thread. `direcao` (`in`=recebida /
  `out`=enviada pela equipe), `texto`, `wa_message_id` (id da Meta, dedupe de webhook
  + correlação de status), `status` (out: `enviada|entregue|lida|falhou`),
  `enviado_por_id`. Cascade delete a partir do contato.

> Todos os três carregam `clinica_id` (multi-tenant). A listagem da inbox **filtra
> explicitamente por `clinica_id`** (defesa em profundidade, além do escopo automático).

### `AuditLog` — trilha de auditoria
`usuario_id`, `acao` (constantes `ACAO_*`), `recurso_tipo`/`recurso_id`,
`detalhes` (**nunca PII**), `ip`, `user_agent`, `criado_em`. **Não tem
`clinica_id`** — o escopo na tela `/auditoria` é feito por join em `Usuario.clinica_id`.

## Fluxo principal (operação da clínica)
```
1. Admin cadastra profissionais (cria o login junto)   /profissionais/novo
2. Recepção/admin cadastra pacientes                   /pacientes/novo
3. Recepção/admin agenda consulta                       /agenda/novo
4. No dia: recepção muda status / faz check-in          /agenda/<id>/status|checkin
5. Profissional registra atendimento (prontuário)       /agenda/<id>/atendimento
   → consulta vira status=atendido automaticamente
6. Recepção/admin registra recebimento                  botão "Receber" na agenda
   → cria LancamentoFinanceiro ligado ao agendamento
```
Fora do fluxo: financeiro (fluxo de caixa / contas), CRM (retornos), relatórios
(sob demanda), agendamento online público (`/c/<slug>/agendar`).
