# 9. Checklist de Go-Live (produção real)

> Passo a passo para sair da **homologação** (Render Free + dados demo) para
> **produção real** (dados de paciente de verdade). A maior parte são ações no
> painel do Render / Cloudflare / HostGator — **não exigem código**.

## ✅ O que já está pronto (código)
- Todo o sistema consolidado em **`master`** e na branch de deploy (mesmo commit).
- Suíte **verde** (286 testes), ruff limpo, auditado por múltiplos agentes.
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

### 5b. Chatbot de ajuda "Nous Assistente" 🤖 (opcional — depende de chave Anthropic)
A feature é **default-OFF**: o código está em produção, mas inerte até ligar.
1. Anthropic Console → API Keys → criar chave (billing pré-pago, ~US$1/1M tokens no Haiku).
2. Render → Environment:
   - `ANTHROPIC_API_KEY` = `sk-ant-...` ⚠️ **direto no Render** (não compartilhar em chat).
   - `AJUDA_IA_ATIVA` = `true`
   - `MODEL_AJUDA` = `claude-haiku-4-5` (default; barato).
3. **Rate-limit em multi-worker:** o limiter do chat é por usuário, mas o storage
   default é `memory://` (por processo). Com mais de 1 worker gunicorn, setar
   `RATELIMIT_STORAGE_URI=redis://...` (o Redis já está no `docker-compose`) pra o
   teto valer global. Sem isso, o limite é N× o configurado (N = nº de workers).
4. Conferir: logado, aparece o balão de ajuda; pergunta "como agendo?" responde;
   pergunta médica/de prontuário (p/ recepção) é recusada (guardrail).

> Sem a chave **ou** com `AJUDA_IA_ATIVA=false`, o widget nem aparece — zero custo.

### 5c. WhatsApp Business (Cloud API) 💬 (opcional — inerte por padrão)
Módulo multi-tenant: cada clínica conecta o número dela e vê as conversas no Nous.
O custo das mensagens é da **clínica** (billing da Meta), não nosso. Default-OFF.
1. Render → Environment (plataforma):
   - `WHATSAPP_ATIVO` = `true` (liga o módulo/menu).
   - `WHATSAPP_VERIFY_TOKEN` = uma string aleatória (handshake do webhook). **Obrigatório.**
   - `WHATSAPP_APP_SECRET` = App Secret do nosso app Meta. ⚠️ **Obrigatório em produção** —
     sem ele o webhook recusa tudo (fail-closed); com ele, valida a assinatura da Meta.
   - `WHATSAPP_ENC_KEY` = uma chave Fernet (recomendado; senão deriva do `SECRET_KEY`).
   - Todos os segredos vão **direto no Render** (não compartilhar em chat).
2. No app da Meta: configurar o webhook → URL `https://nousclinical.com/whatsapp/webhook`
   + o mesmo `WHATSAPP_VERIFY_TOKEN`; assinar o campo `messages`.
3. Cada clínica: Admin → WhatsApp → **Configurar conexão** (cola `phone_number_id` + token).
4. Modelo de onboarding e custos detalhados em [docs/10-whatsapp-integracao.md](10-whatsapp-integracao.md).

> **Retenção (LGPD):** conversas de WhatsApp guardam telefone (PII) e texto. Definir
> política de expurgo antes de operar com volume (hoje sem TTL automático).

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
