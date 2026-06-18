# 9. Checklist de Go-Live (produção real)

> Passo a passo para sair da **homologação** (Render Free + dados demo) para
> **produção real** (dados de paciente de verdade). A maior parte são ações no
> painel do Render / Cloudflare / HostGator — **não exigem código**.

## ✅ O que já está pronto (código)
- Todo o sistema consolidado em **`master`** e na branch de deploy (mesmo commit).
- Suíte **verde** (271 testes), ruff limpo, auditado por múltiplos agentes.
- `ProductionConfig` já endurecido: `DEBUG=False`, cookies `Secure`/`HttpOnly`/
  `SameSite`, pool de conexão, CSP estrita, CSRF, rate-limit, Argon2id.
- Storage S3/R2 implementado (só falta ligar as chaves).
- Multi-tenant com escopo automático por clínica; LGPD (prontuário/exames restritos).

---

## 🚦 Passos para o go-live

### 1. Desligar o seed de demonstração ⚠️ (Render → Environment)
Hoje cada deploy popula clínicas/superadmin **de demonstração**. Em produção:
- `RUN_SEED` → **`false`**
- `RUN_DEMO` → **`false`**

> As clínicas demo já existentes no Postgres **não são apagadas** por isso (só
> param de ser recriadas). Se quiser removê-las de fato, faça depois pelo painel
> de Clínicas (superadmin) ou direto no banco.

### 2. Storage persistente — Cloudflare R2 🪣 (depende do cartão do sócio)
Sem isso, logo e exames somem no redeploy (disco efêmero no Free).
1. Cloudflare → R2 → criar bucket **`nous-clinical`**.
2. Criar API Token (Object Read & Write) → copiar Endpoint + Access Key + Secret.
3. Render → Environment:
   - `STORAGE_BACKEND` = `s3`
   - `S3_ENDPOINT_URL`, `S3_BUCKET=nous-clinical`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION=auto`
   - ⚠️ As chaves vão **direto no Render** (não compartilhar em chat).

### 3. Plano pago (sair do Free) 💳 — Cenário 2 do estudo
- Render **Starter** (web, ~US$7) + **Postgres Basic** (~US$6) → ~R$ 75/mês.
- Evita o "spin-down" (app dormindo) e o **Postgres Free expira em 90 dias**.
- Ver comparativo em [docs/08-hospedagem-e-custos.html](08-hospedagem-e-custos.html).

### 4. Domínio `nousclinical.com` 🌐
- DNS já configurado (A `@` → Render, CNAME `www`).
- Render → Settings → **Custom Domain** → adicionar `nousclinical.com` e `www`.
- Conferir o certificado TLS emitir (automático).
- Setar `PUBLIC_BASE_URL=https://nousclinical.com` (links de e-mail/WhatsApp).

### 5. Branch de deploy (opcional)
- Hoje o Render faz deploy de **`feat/nous-rebrand-financeiro`** (= `master`).
- Para usar `master` como produção: trocar a branch no painel do Render (ou em
  `render.yaml`) e re-sincronizar. Sem pressa — as duas apontam para o mesmo código.

### 6. Primeiro acesso real 👤
- Criar o **superadmin real**: `flask criar-superadmin --email ... --senha ...`
  (ou via shell do Render). Trocar a senha demo.
- Cadastrar a **primeira clínica real** e o admin dela.
- Conferir `SECRET_KEY` no Render é `generateValue` (persistente) — **não trocar**,
  senão derruba todas as sessões.

### 7. Verificação final
- `GET /health` → `status: ok` + `migration_head` = o head atual.
- Login admin real → Agenda (Dia/Grade/Semana), Bloqueios, Pacientes, Financeiro,
  Relatórios, CRM (Retornos/Aniversariantes), Cadastro de Itens (Salas/Convênios).
- Subir um logo e confirmar que **persiste** após um redeploy (valida o R2).

---

## 🔁 Rollback
- Deploy quebrado → Render → **Rollback** para o deploy anterior (1 clique).
- Migration problemática → `flask db downgrade -1` (as migrations são batch-safe).
- Dados → a portabilidade está documentada em [docs/08](08-hospedagem-e-custos.html)
  (pg_dump/restore + reapontar DNS).

> **Resumo:** o código está pronto. O go-live é, na ordem: desligar demo (1) →
> ligar R2 (2) → plano pago (3) → domínio (4). Os itens 5–7 são acabamento.
