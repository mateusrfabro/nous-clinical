# Nous Clinical — Status de Produção e Pendências

> **Documento interno (PGS).** Para alinhamento entre os sócios. Não vai para o cliente.
> Atualizado em: 23/06/2026 (noite) · Site: **nousclinical.com** · Hospedagem: **Render**

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
- ✅ **Manual do Usuário** (PDF) — entregue às clínicas.
- ✅ **Documentação técnica e de projeto** — atualizada.

## 2. Qualidade e segurança

- ✅ **Suíte de testes: 328 verdes.**
- ✅ **Auditoria adversarial multi-agente** (módulo fiscal + Suporte): **23 possíveis
  problemas levantados → 0 confirmados** após verificação adversarial.
- ✅ **Nenhum segredo vazado no repositório** (credenciais só em variáveis de ambiente).
- ✅ WhatsApp já passara por auditoria (1 vazamento cross-tenant achado e **corrigido**).

## 3. Pendências de produção (decisões/ações de vocês)

### 🔴 Antes de uso real
1. **Senha do super-admin** — já foi trocada; **trocar de novo** por uma que não tenha
   passado por chat. (`RUN_SEED`/`RUN_DEMO` já estão **`false`** ✓ — não recria mais demo.)

### 🟡 Infra e custo — TEM PRAZO
2. **Plano pago do Render — ANTES dos ~90 dias.** O banco grátis **expira e perde os
   dados**. É a pendência **mais urgente** para uso real. (~US$ 7–15/mês banco + web.)
3. **Armazenamento (R2/S3)** — logo e exames hoje somem a cada atualização; configurar
   um bucket barato (Cloudflare R2 ou S3) e preencher as chaves no painel.

### 🟢 Ativar quando quiserem (estão prontos, desligados)
4. **Assistente com IA** (opcional) — o Suporte gratuito já atende; se quiserem o modo IA,
   basta colar a `ANTHROPIC_API_KEY` no Render (custo da PGS, centavos/mês).
5. **WhatsApp por clínica** — já ligado; cada clínica conecta o próprio número.

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
> regime tributário, alíquota de ISS e código de serviço** (medicina 4.01 / clínica 4.03).

## 5. Resumo de custos

| Item | Custo hoje | Quando "liga" |
|---|---|---|
| Sistema (Render web + banco) | R$ 0 (free) | ~US$ 7–15/mês cada (plano pago) |
| Suporte Nous (ajuda) | **R$ 0 sempre** (sem IA) | — |
| Assistente com IA (opcional) | R$ 0 (desligado) | centavos/mês (PGS) ao colar a chave |
| WhatsApp | R$ 0 (inerte) | pago pela **clínica** à Meta |
| Nota Fiscal (gateway) | R$ 0 (desligado) | mensalidade do gateway quando emitir (PGS/clínica) |
| Armazenamento (R2/S3) | R$ 0 (efêmero) | centavos/mês ao configurar |

---

**Resumo de uma linha:** WhatsApp, Suporte e a Fase 1 da Nota Fiscal estão **em produção,
testados e auditados** (tudo desligado/seguro). O mais urgente é o **plano pago do Render**
(prazo dos ~90 dias); e a **emissão de NF** só fecha quando tivermos um **certificado A1 de
teste**.
