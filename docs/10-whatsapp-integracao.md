# 10. WhatsApp Business (Cloud API) — pesquisa + arquitetura

> Como acoplar o WhatsApp **de cada clínica** dentro do Nous (multi-tenant), com
> as conversas visíveis no sistema. Pesquisa de casos reais + a decisão que tomamos.
> A integração é construída **inerte** (desligada por flag) — custo zero até uma
> clínica conectar um número de verdade.

## TL;DR (decisão)
1. **Começar com token colado manualmente** (a clínica gera um token de System User
   no Meta Business e cola no Nous, junto com o `phone_number_id`). Zero burocracia
   do nosso lado, scaffold já pronto.
2. **Evoluir para Embedded Signup** (botão "Conectar WhatsApp") quando valer a pena —
   exige nos cadastrarmos como **Tech Provider** + Business Verification + App Review.
3. **Webhook único** roteia por `phone_number_id` → clínica dona. Padrão confirmado
   em projetos reais (OpenBSP, Chatwoot).

---

## 1. Embedded Signup (o padrão "de verdade" dos SaaS)
É o fluxo onde o cliente clica **"Conectar WhatsApp"** no nosso app, faz login no
Facebook num popup (JS SDK da Meta + um `configuration_id` do nosso app) e autoriza.
No callback recebemos um **`code`**, que trocamos **server-side** por um access token
via Graph API, obtendo o **WABA ID** e o **`phone_number_id`** do cliente — **sem** o
cliente criar um Meta App próprio.

- **Requisitos da Meta:** cadastro como **Tech Provider/Solution Partner**, **Business
  Verification**, **App Review** com *advanced access* nas permissões
  `whatsapp_business_management` e `whatsapp_business_messaging`.
- **Limite de onboarding:** por padrão **10** novos clientes por janela de 7 dias;
  após Business Verification + App Review + Access Verification sobe pra **200**/7 dias.
- Doc oficial: [Embedded Signup — Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview)
  e [Onboarding como Tech Provider](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-customers-as-a-tech-provider/).

## 2. Alternativa MVP: token colado manualmente
A clínica cria o próprio app/System User na Meta e cola **token + `phone_number_id`**
no Nous (tela de Configurações → WhatsApp, só admin/gestora).
- **Prós:** zero App Review **do nosso lado**; dá pra ligar hoje pra 1 cliente piloto.
- **Contras:** onboarding técnico difícil pra clínica leiga; a clínica gerencia a
  expiração/escopo do token. Bom pra **piloto**, ruim pra **escala**.
- É **exatamente** o que o scaffold atual faz. Migrar pra Embedded Signup depois não
  joga fora nada (o modelo de dados é o mesmo: `phone_number_id` + token por clínica).

## 3. Webhook único multi-tenant (como roteia)
Um só endpoint (`/whatsapp/webhook`) recebe eventos de **todas** as contas:
- **GET** = handshake: comparar `hub.verify_token` com o nosso `WHATSAPP_VERIFY_TOKEN`,
  devolver `hub.challenge`.
- **POST** = eventos: validar `X-Hub-Signature-256` (HMAC-SHA256 do corpo cru com o
  **App Secret**), depois ler `entry[].changes[].value.metadata.phone_number_id` e
  achar a `WhatsAppConta` dona → gravar a mensagem **na clínica certa**.

## 4. Custos reais (2026) — quem paga
Desde **jul/2025** a Meta cobra **por mensagem** (template entregue), não mais por
"conversa de 24h". Valores-base no **Brasil** (USD; BRL local previsto p/ 2º semestre 2026):

| Categoria | Custo aprox. | Observação |
|---|---|---|
| **Service** (resposta dentro de 24h da msg do cliente) | **grátis** | a inbox/atendimento cabe aqui |
| **Utility** (lembrete, confirmação) | ~US$0,008 | template utilitário |
| **Authentication** (OTP) | ~US$0,0315 | |
| **Marketing** | ~US$0,0625 | + caro |
| Clique-pra-WhatsApp (anúncio) | grátis por 72h | |

- BSP (se usarmos intermediário tipo Twilio/360dialog) adiciona ~US$0,003–0,010/msg.
  Indo **direto na Cloud API** (nosso caso), não há markup de BSP.
- **Quem paga:** a conta de WhatsApp é **da clínica** → o **billing da Meta é da clínica**
  (cartão dela no Meta Business). O Nous não paga as mensagens. Responder dentro da
  janela de 24h (atendimento) é **grátis** — o uso típico de recepção.
- Fontes: [Message Central — Brasil 2026](https://www.messagecentral.com/blog/whatsapp-business-api-pricing-in-brazil),
  [Chatarmin 2026](https://chatarmin.com/en/blog/whats-app-api-pricing).

## 5. Projetos open-source de referência (arquitetura)
- **OpenBSP** ([github.com/matiasbattocchia/open-bsp-api](https://github.com/matiasbattocchia/open-bsp-api)) —
  **Unlicense (domínio público)**. Multi-tenant: `organizations → addresses
  (phone_number_id) → contacts → conversations → messages`; webhook roteia por
  `phone_number_id`. **É o espelho da nossa modelagem.**
- **Chatwoot** — inbox multicanal madura (modelo inbox/contact/conversation). Ref. de UX de caixa de entrada.
- **Evolution API** ([github](https://github.com/evolution-foundation/evolution-api)) — gateway WhatsApp (Cloud API + Baileys).
- **whatsapp-cloud-inbox** ([github.com/gokapso/whatsapp-cloud-inbox](https://github.com/gokapso/whatsapp-cloud-inbox)) —
  inbox estilo WhatsApp Web pra Cloud API, com janela de 24h e templates.

## 6. Como o Nous implementa (este scaffold)
- **Modelo:** `WhatsAppConta` (1/clínica: `phone_number_id` único, token **cifrado**
  em repouso), `WhatsAppContato` (a thread, casado a `Paciente` por telefone),
  `WhatsAppMensagem` (in/out, status, `wa_message_id`). Tudo escopado por `clinica_id`.
- **Onboarding (hoje):** Configurações → WhatsApp (admin cola `phone_number_id` + token).
- **Inbox:** lista de conversas + thread + responder (recepção/admin).
- **Inerte:** `WHATSAPP_ATIVO=false` por padrão → o menu nem aparece e nada é enviado.
  Liga global no Render + `ativo=True` por clínica. Segredos (`WHATSAPP_VERIFY_TOKEN`,
  `WHATSAPP_APP_SECRET`) vão **direto no Render**.
- **Próximo passo (escala):** trocar o "colar token" por **Embedded Signup** (botão),
  reaproveitando todo o resto.
