# Nous Clinical — Status de Produção e Pendências

> **Documento interno (PGS).** Para alinhamento entre os sócios. Não vai para o cliente.
> Atualizado em: 01/07/2026 · Site: **nousclinical.com** · Hospedagem: **Render**

---

## 1. O que já está EM PRODUÇÃO

Tudo abaixo está **no ar** no `nousclinical.com` (deploy automático a cada `push`; as
migrações de banco rodam sozinhas). Recursos novos sobem **inertes/seguros** — só
"acendem" quando alguém liga.

- ✅ **WhatsApp integrado** — cada clínica conecta o próprio número. Inerte até conectar;
  custo das mensagens é da clínica (Meta).
- ✅ **Suporte Nous** — ajuda de uso **de custo zero** (busca na base local, sem IA),
  **sempre ligada** para a equipe. Existe também um assistente com IA opcional, **desligado**.
- ✅ **Módulo de Nota Fiscal (NFS-e) — Fase 1** — configuração do emitente por clínica +
  cadastro no emissor (Nuvem Fiscal). **Desligado em produção** (`NF_ATIVO` off): não
  aparece no menu até ser ligado, e a **emissão ainda não está pronta** (ver §4).
- ✅ **Agenda — visão Quadro (Kanban)** — 4ª forma de ver a agenda, por status, com
  arrastar-e-soltar entre colunas. Soma-se a Dia/Grade/Semana.
- ✅ **Painel do gestor com KPIs do dia** — faturamento de hoje, taxa de faltas, a receber
  em atraso e ocupação por profissional (só admin/recepção).
- ✅ **Financeiro avançado** — **conciliação bancária** (importa extrato OFX/CSV, casa com
  os lançamentos: sugestão automática + manual + painel de divergências) e **fechamento de
  caixa diário** (esperado por forma de pagamento × contado, com divergência). O relatório
  de **repasse por profissional** calcula a comissão por profissional e oferece um atalho **"Lançar
  repasse"** que abre a despesa **pré-preenchida** (o admin confere e salva).
- ✅ **Lembrete de consulta automático** — por **WhatsApp** (template aprovado) ou e-mail;
  reduz faltas. (WhatsApp exige o template HSM aprovado pela clínica; sem ele, cai no e-mail.)
- ✅ **Concierge — mensagens de retorno/reativação** — botão **"Gerar mensagem"** nos painéis
  de **Retornos** (CRM) e **Risco de Evasão** (Relatórios): gera um rascunho personalizado, a
  recepção revisa e envia por WhatsApp/e-mail. **Custo ZERO por padrão** (modo template; sem API).
  Há um **modo IA opcional desligado** (`CONCIERGE_ATIVO` + `ANTHROPIC_API_KEY`) pra frases mais
  variadas — centavos/mensagem se ligado. Não lê prontuário (LGPD-safe); auditado só por metadado.
- ✅ **Landing comercial pública** — a home `/` virou página de vendas honesta (módulos,
  diferenciais, segurança/LGPD, faixa de transparência), gerada do `COMERCIAL-NOUS.md`. O CTA
  usa `CONTATO_COMERCIAL` (WhatsApp/e-mail/form do comercial); sem ele, cai em "Entrar".
- ✅ **Padronização de UI/UX e acessibilidade** — design system consistente (botões, valores
  alinhados, menu de ações "⋯", segmented control) e correções de contraste/teclado (WCAG).
- ✅ **Manual do Usuário** — texto + **screenshot real da visão Quadro** e **PDF regerado**
  (`Manual-Nous-Clinical.pdf`).
- ✅ **Landing comercial otimizada p/ conversão** — CTA "Agendar demonstração" → WhatsApp do
  comercial, navbar contextual, message match, barra sticky no mobile. Ver `docs/CAMPANHA-COLD-EMAIL.md`
  (estratégia + copy + LGPD/Brevo do cold e-mail).
- ✅ **Documentação técnica, comercial e de projeto** — atualizada
  (`docs/COMERCIAL-NOUS.md` para o comercial; `docs/12-conciliacao-e-caixa.md` técnica).
- ✅ **Hardening custo-zero (01/07)** — rodada de auditoria com agentes + melhorias sem custo:
  - **2FA (verificação em duas etapas)** por app autenticador — opcional por usuário, com QR e
    **códigos de recuperação**. Recomendado p/ admin. (Manual: *Meu Perfil*.)
  - **Anonimização de paciente (LGPD art. 18 — direito ao esquecimento)** — admin apaga PII +
    prontuário + exames e **preserva o financeiro** (obrigação fiscal). Auditado.
  - **Login mais seguro** — bloqueio da conta após 5 erros (15 min) + **aviso por e-mail** de
    acesso de novo dispositivo.
  - **Dependência com CVE corrigida** (`cryptography` 46→48; 5 CVEs) e **gate de segurança do
    CI agora bloqueante** (bandit + pip-audit); o CI passou a **rodar na branch de deploy**.
  - **Testes rodam também contra Postgres** no CI (paridade dev/prod) — passou sem divergência.

## 2. Qualidade e segurança

- ✅ **Suíte de testes: 419 verdes** (inclui IDOR multi-tenant, parse de dinheiro BR, Concierge
  fail-closed, **2FA**, **anonimização LGPD**, **lockout de login** e conciliação/dedup OFX).
  A suíte roda em SQLite **e em Postgres** (paridade com produção).
- ✅ **Auditoria adversarial multi-agente** em várias rodadas (fiscal, Suporte, UI/perf/
  segurança/a11y, financeiro, e o **núcleo inteiro** — tenant/auth/financeiro/uploads/agenda):
  **0 Crítico/Alto explorável**. Achados verificados e **corrigidos**:
  - **Multi-tenant fail-closed** — usuário sem clínica não "vê tudo" (sentinela); guard explícito
    de clínica (`get_da_clinica`) nas rotas de paciente/agenda/prontuário/exame (defesa contra
    IDOR por identity-map).
  - **Dinheiro** — ponto de milhar BR sem vírgula não vira mais centavo (`1.234` = R$ 1.234) no
    caixa e na conciliação; conciliação não casa tipo incompatível nem duplica receita.
  - **Rate-limit** em produção usa Redis (não `memory://` por-worker).
- ✅ **Nenhum segredo vazado no repositório** (credenciais só em variáveis de ambiente).
- ✅ WhatsApp já passara por auditoria (1 vazamento cross-tenant achado e **corrigido**).
- 🟡 **Mapeado p/ evoluir (não-bloqueante):** agendamento público tem só honeypot+rate-limit
  contra spam (avaliar CAPTCHA/confirmação se houver abuso).
- ✅ **Defesa em profundidade** no financeiro: guard explícito de `clinica_id` nas
  mutações, além do escopo automático por clínica.

## 3. Pendências de produção (decisões/ações de vocês)

### 🔴 Antes de uso real
1. **Senha do super-admin** — já foi trocada; **trocar de novo** por uma que não tenha
   passado por chat. (`RUN_SEED`/`RUN_DEMO` já estão **`false`** ✓ — não recria mais demo.)

### 🟡 Infra e custo — TEM PRAZO
2. **Plano pago do Render — ANTES dos ~90 dias.** O banco grátis **expira e perde os
   dados**. É a pendência **mais urgente** para uso real. (~US$ 7–15/mês banco + web.)
3. **Armazenamento (R2/S3)** — ✅ **CONCLUÍDO e confirmado em produção.** Cloudflare R2
   (bucket `nous-clinical`, conta do sócio Lucas), 4 chaves no Render, upload de logo
   testado ao vivo (arquivo confirmado no bucket via API). Logo e exames agora
   **persistem** entre deploys. Free tier 10 GB. *(O token do R2 só acessa o bucket
   `nous-clinical` — escopo mínimo; sem ação pendente de rotação.)*

### 🟢 Ativar quando quiserem (estão prontos, desligados)
4. **Assistente com IA** (opcional) — o Suporte gratuito já atende; se quiserem o modo IA,
   basta colar a `ANTHROPIC_API_KEY` no Render (custo da PGS, centavos/mês).
5. **WhatsApp por clínica** — já ligado; cada clínica conecta o próprio número.
6. **Concierge — modo IA** (opcional) — o botão "Gerar mensagem" **já funciona de graça**
   (templates). Se quiserem frases geradas por IA, `CONCIERGE_ATIVO=true` + `ANTHROPIC_API_KEY`
   no Render (centavos/geração, PGS). **Decisão atual: NÃO ligar** — sem custo p/ ninguém agora.
7. **CTA da landing** — setar `CONTATO_COMERCIAL` (ex.: link `https://wa.me/55...` do comercial
   ou `mailto:`) pra o botão "Falar com a gente" apontar pro canal certo.

### 👥 Acesso
6. **Adicionar o Lucas como colaborador** no repositório (pros links dos PDFs abrirem).

## 4. Módulo de Nota Fiscal — onde está e o que falta

| Etapa | Status |
|---|---|
| Pesquisa + decisão de gateway (Nuvem Fiscal + Focus de reserva) | ✅ |
| Adaptador + autenticação | ✅ validado ao vivo (sandbox) |
| Config fiscal por clínica (tela admin) | ✅ em produção (inerte) |
| Cadastro do emitente no emissor | ✅ validado ao vivo (sandbox) |
| **Emissão da nota (Fase 2)** | ⛔ **bloqueada** |

> **Bloqueio da Fase 2:** emitir exige **certificado digital A1 (e-CNPJ)** desde o
> primeiro passo — mesmo no ambiente de teste. **Para fechar a emissão, precisamos de um
> certificado A1 de teste** (o da própria PGS serve). Sem ele, não dá para construir e
> **validar** a emissão. Quando houver o A1, retomamos e fechamos a Fase 2.
>
> **Quando lançar (depois da Fase 2):** ligar com `NF_ATIVO=true` + credenciais da Nuvem
> Fiscal no Render. Cada clínica precisará de: **certificado A1, inscrição municipal,
> regime tributário, alíquota de ISS e código de serviço** — que **varia por profissão**
> (ex.: medicina 4.01 / clínica 4.03 / odontologia 4.02).

## 5. Resumo de custos

| Item | Custo hoje | Quando "liga" |
|---|---|---|
| Sistema (Render web + banco) | R$ 0 (free) | ~US$ 7–15/mês cada (plano pago) |
| Suporte Nous (ajuda) | **R$ 0 sempre** (sem IA) | — |
| Assistente com IA (opcional) | R$ 0 (desligado) | centavos/mês (PGS) ao colar a chave |
| WhatsApp | R$ 0 (inerte) | pago pela **clínica** à Meta |
| Nota Fiscal (gateway) | R$ 0 (desligado) | mensalidade do gateway quando emitir (PGS/clínica) |
| Armazenamento (R2/S3) | R$ 0 (free tier 10 GB) ✅ ativo | centavos/mês só se passar de 10 GB |

---

**Resumo de uma linha:** WhatsApp, Suporte, a Fase 1 da Nota Fiscal e o **armazenamento R2
(logo/exames persistem)** estão **em produção, testados e auditados**. O único item de infra
**com prazo** é o **plano pago do banco no Render** (~90 dias, senão perde os dados); e a
**emissão de NF** só fecha quando tivermos um **certificado A1 de teste**.
