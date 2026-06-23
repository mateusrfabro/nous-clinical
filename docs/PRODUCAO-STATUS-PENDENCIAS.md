# Nous Clinical — Status de Produção e Pendências

> **Documento interno (PGS).** Para alinhamento entre os sócios. Não vai para o cliente.
> Atualizado em: 23/06/2026 · Site: **nousclinical.com** · Hospedagem: **Render** (Oregon)

---

## 1. O que foi entregue nesta rodada

- ✅ **WhatsApp integrado** — cada clínica conecta o próprio WhatsApp Business e
  recebe/responde mensagens dentro do sistema. Testado (304 testes verdes), token
  guardado cifrado, isolado por clínica.
- ✅ **Manual do Usuário completo** — guia tela por tela, com prints reais e PDF, para
  entregar às clínicas (já enviado ao grupo).
- ✅ **Documentação técnica atualizada** (uso interno) — arquitetura, domínio,
  multi-tenant, deploy, custos.

---

## 2. Alinhamento Local ↔ Produção

O deploy no Render é **automático ao dar `push`** na branch `feat/nous-rebrand-financeiro`
(que é a branch principal do projeto). Ao subir, o sistema **roda sozinho** a atualização
do banco (as 3 tabelas novas do WhatsApp) e sobe a nova versão.

| Item | Local | Produção (hoje) | Depois do push |
|---|:---:|:---:|:---:|
| Código WhatsApp + Manual | ✅ | ❌ ainda não | ✅ |
| Tabelas do WhatsApp no banco | ✅ | ❌ | ✅ (migração automática) |
| WhatsApp ligado (tela de conexão) | — | ❌ | ✅ (inerte até conectar) |
| Chatbot "armado" (sem chave) | — | ❌ | ✅ (liga ao colar a chave) |
| Re-seed de dados demo | desligado | ⚠️ **ligado** | ✅ desligado |

> **Faltam 4 commits irem para o ar** (WhatsApp, Manual, doc de domínio, config de prod).
> Assim que autorizado, o push leva tudo e o Render atualiza em poucos minutos.

---

## 3. Pendências (o que falta para ficar 100%)

### 🔴 Segurança — resolver antes de uso real
1. **Super-admin com senha fraca em produção.** Os primeiros deploys criaram um
   super-admin de demonstração (`super@nous.com` / senha padrão fraca) no site real.
   **Ação:** trocar a senha (ou apagar essa conta e criar a real, de vocês dois) e
   confirmar que `RUN_SEED` e `RUN_DEMO` estão **`false`** no painel do Render — senão
   o próximo deploy recria isso.
2. **Clínicas de demonstração no site real.** Os seeds de validação criaram clínicas
   fictícias em produção. **Ação:** decidir se limpamos esses dados de teste antes de
   abrir para clientes.

### 🟡 Infra e custo — decisão de sócio
3. **Plano gratuito vai expirar.** O banco de dados grátis do Render **expira em ~90
   dias e perde os dados**; o site grátis "dorme" após 15 min parado. Para clínica de
   verdade usando, precisamos subir para plano pago (banco + web, na faixa de
   ~US$ 7–15/mês cada). **Decisão:** quando migrar para o pago.
4. **Armazenamento de arquivos (logo e exames).** Hoje os arquivos caem no disco do
   servidor, que **é apagado a cada atualização**. Para preservar logos e exames,
   precisamos de um bucket de armazenamento (Cloudflare R2 ou S3 — barato).
   **Ação:** criar o bucket e preencher as 4 chaves no painel.

### 🟢 Ativar funcionalidades — quando quiserem
5. **Chatbot de ajuda.** Já vai "armado" para produção. Para ligar de fato, basta
   **colar a chave da API** no painel do Render (custo da PGS — centavos/mês). Enquanto
   a chave não for colada, fica desligado e sem custo.
6. **WhatsApp por clínica.** Já fica ligado e pronto. Cada clínica conecta o **próprio**
   número (cola o identificador e o token obtidos no painel da Meta Business). Custo das
   mensagens é da clínica; responder em até 24h é grátis.

---

## 4. Checklist de go-live (passo a passo, no painel do Render)

1. [ ] **Variáveis** — confirmar `RUN_SEED=false` e `RUN_DEMO=false`.
2. [ ] **Super-admin** — trocar a senha do `super@nous.com` (ou criar o login real dos
       sócios e remover o demo).
3. [ ] **Banco** — subir do plano free para o pago (antes dos ~90 dias).
4. [ ] **Armazenamento** — criar bucket (R2/S3) e preencher `S3_*` no painel.
5. [ ] **(Opcional) Chatbot** — colar `ANTHROPIC_API_KEY` para ativar.
6. [ ] **Deploy** — autorizar o `push` (leva tudo ao ar; migração roda sozinha).
7. [ ] **Validar** — abrir `nousclinical.com/health` e fazer um login de teste.

---

## 5. Resumo de custos (para não ter surpresa)

| Item | Custo hoje | Quando "liga" |
|---|---|---|
| Sistema (Render web + banco) | R$ 0 (plano free) | ~US$ 7–15/mês cada ao migrar p/ pago |
| Chatbot de ajuda | R$ 0 (desligado) | Centavos/mês (PGS paga) ao colar a chave |
| WhatsApp | R$ 0 (inerte) | Pago pela **clínica** à Meta; responder em 24h é grátis |
| Armazenamento (R2/S3) | R$ 0 (disco efêmero) | Centavos/mês ao configurar o bucket |

---

**Resumo de uma linha:** o produto está pronto e testado; o que falta são **ações no
painel do Render** (segurança + plano pago + armazenamento) e o **push** para levar as
novidades ao ar — tudo sobe desligado/seguro, e cada feature só "acende" quando a gente
(ou a clínica) conectar.
