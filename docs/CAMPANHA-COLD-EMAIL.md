# Campanha de aquisição — Cold E-mail B2B (Nous Clinical)

> **Documento interno (PGS).** Playbook pra vender o Nous a clínicas pequenas via cold e-mail.
> Consolida 4 análises (estratégia/oferta, conformidade LGPD + entregabilidade Brevo, copy,
> conversão da LP). Honesto: o Nous resolve gestão hoje; **NF-e (emissão) é roadmap** e nunca
> entra como motivo de compra.

## 0. Parâmetros da campanha
- **Público (ICP):** clínicas/consultórios de **1–3 profissionais** (saúde em geral — medicina, odontologia, psicologia, fisio, nutrição etc.), dono põe a mão na gestão.
- **Oferta do clique:** **demonstração gratuita** (reposicionada como "diagnóstico de 20 min").
- **Canal:** cold e-mail → landing (`/` ou `/produto`) → **WhatsApp** (agendar a demo).
- **Domínio de envio:** **subdomínio dedicado** (`enviar.nousclinical.com`) — o `nousclinical.com`
  principal fica só pra transacional/relacional.

---

## 1. ⚠️ Decisão crítica: Brevo + cold não combinam
**O Brevo proíbe cold/lista comprada nos Termos de Uso.** Disparar frio (mesmo de fonte pública)
pelo Brevo = **risco real de suspensão da conta** se a reclamação subir. Caminhos, do mais seguro
ao mais arriscado:
1. **(Recomendado p/ início)** Outbound mirado e pequeno: começar pelos leads mais "mornos"
   (com alguma referência/indicação), volume baixo, e-mail + toque humano (WhatsApp/ligação).
2. **Brevo com disciplina rígida:** dá pra usar, sendo conservador no volume e impecável na
   higiene/opt-out — aceitando o risco de termos.
3. **Cold em escala:** ferramenta feita pra cold (Instantly/Smartlead) com inboxes dedicados;
   o Brevo fica só pra base com consentimento.

---

## 2. Estratégia de oferta — "demo" vira "diagnóstico de 20 min"
Não vender "demonstração" (= "mais um vendedor querendo 40 min"). Vender:
> **"20 minutos pra te mostrar onde sua clínica perde dinheiro na operação — com os seus números."**

Na call, mostrar **3 telas de impacto financeiro** (não tour de features):
1. **Painel do gestor** — "abre o sistema e em 5s sabe quanto entrou hoje, faltas, ocupação".
2. **Repasse por profissional + DRE** — "fecha o repasse do mês sem planilha".
3. **CRM de retorno/evasão** — "lista de quem sumiu + botão pra chamar de volta".

Regras: prometer **20 min** (não 40); humano conduz (não SDR robô); **honestidade como
fechamento** ("NF-e ainda não emite, é roadmap" gera confiança que o concorrente não tem).

### Funil e onde o lead esfria
`cold e-mail → LP → demo agendada → demo realizada → fechamento`. Vazamentos: (1) não abre/clica;
(2) clica e não agenda; (3) **agenda e não aparece — maior vazamento**, mata com lembrete 24h+1h
e slot ≤3 dias; (4) demo vira "tour" sem pedir a venda; (5) "vou pensar".

### Qualificação
**Vale a demo:** 1–3 profissionais, hoje em planilha/sistema abandonado, com recepção e/ou convênio e
repasse, especialidade com retorno recorrente. **Descartar:** rede/hospital, quem exige NF-e como
condição HOJE, solo sem recepção/convênio, quem quer on-premise.

### Preço (sugestão a validar — material comercial diz "sob consulta")
| Plano | Perfil | Faixa/mês sugerida |
|---|---|---|
| Essencial | 1 profissional | R$ 150–250 |
| Clínica | 2–3 profissionais | R$ 350–600 |
| Plus | 3 profissionais + opcionais | R$ 600–900 |

Ancorar contra o **custo do problema** (falta não cobrada, repasse errado, paciente que some),
não contra concorrente. Fechamento com degrau de baixo risco (onboarding incluso / sem fidelidade).

### Expectativa honesta (não vender 5% pro sócio)
Cold frio realista: **~1 cliente a cada ~1.000 e-mails** na 1ª rodada. Alavanca = **qualificar a
lista** + **subir o show rate** (lembretes), não "mandar mais".

---

## 3. Conformidade LGPD (cold B2B)
Cold B2B no Brasil **não é proibido**, mas exige base legal + salvaguardas:
- **Base legal:** **legítimo interesse** (Art. 7º IX) + **LIA documentada** (por que é legítimo,
  necessário, não atropela o titular).
- Priorizar **e-mail institucional** (`contato@`, `recepcao@`) sobre nominal de pessoa física.
- **Obrigatório:** remetente identificado (Nous + CNPJ + contato), finalidade explícita no corpo,
  **opt-out funcional** que remove na hora, atender pedido de exclusão (Art. 18), **registrar a
  origem** de cada lead (Maps/Receita/conselho), **nenhum dado sensível**.
- **Não:** comprar lista, esconder/falsear remetente, assunto enganoso, insistir em quem pediu sair.

---

## 4. Entregabilidade no Brevo (subdomínio dedicado)
- **DNS:** **SPF** (`v=spf1 include:spf.brevo.com mx ~all`, um só por domínio) + **DKIM** (TXT/CNAME
  do Brevo) + **DMARC** em `_dmarc.enviar.nousclinical.com` começando `p=none` (monitorar) →
  `quarantine` → `reject`. Verificar tudo verde no Brevo antes do 1º envio. Remetente:
  `contato@enviar.nousclinical.com`, **reply-to monitorado por humano**.
- **Warmup (rampa):** dia 1–3: 10–20/dia (pra contatos que abrem/respondem); dia 4–7: 20–40;
  semana 2: 40–80; semana 3: 80–150; semana 4+: subir ≤30–50%/etapa. Nunca dobrar de um dia pro outro.
- **Higiene:** validar a lista antes (ZeroBounce/NeverBounce/MillionVerifier); **bounce < 2%**.
- **Conteúdo anti-spam:** texto plano > HTML pesado; 1 link + unsubscribe; sem encurtador; sem
  CAPS/`!!!`/"grátis/promoção/clique aqui"; rodapé com identificação; personalizar (clínica/cidade).
- **Limites (PARE e corrija):** bounce > 3–5%; **reclamação de spam > 0,1% → risco de suspensão**;
  open despencou → provável spam, reduza volume e volte ao warmup.

---

## 5. Sequência de cold e-mail (pronta, honesta) — texto plano
Tokens: `{{primeiro_nome}}`, `{{clinica}}`, `{{cidade}}`, `{{remetente}}`. **Opt-out em todos.**

### E1 — Abertura (dor: gestão rouba tempo)
**Assunto:** Gestão da {{clinica}} ainda mora numa planilha?
> Olá, {{primeiro_nome}}, tudo bem?
> Vi que a {{clinica}}, em {{cidade}}, atende com equipe enxuta — e clínica enxuta carrega a gestão
> na mão: agenda num lugar, pagamentos em outro, paciente que some sem ninguém perceber.
> O Nous Clinical junta agenda, pacientes, prontuário e financeiro num sistema só, com cada um vendo
> só o que é dele (prontuário restrito, como a LGPD exige).
> Faz sentido eu te mostrar em ~20 min, sem compromisso, como ficaria na sua rotina? Responda
> "pode mandar" que envio o link.
> {{remetente}} — Nous Clinical
> *Se não for o assunto certo, responda "sair" que não escrevo de novo.*

### E2 — Follow-up (dinheiro / fechamento de caixa)
**Assunto:** O caixa da {{clinica}} fecha batendo todo dia?
> {{primeiro_nome}}, voltando rápido. A parte que mais escapa em consultório pequeno não é a agenda
> — é o dinheiro: recebimento que ninguém marcou, extrato que não bate, surpresa no fim do mês.
> No Nous o financeiro tem fluxo de caixa, contas a pagar/receber e **conciliação do extrato do
> banco (OFX/CSV)** — concilia o que bate e aponta a divergência. Mais o fechamento de caixa do dia.
> Quer ver essa parte primeiro, na demo? Respondo com o link hoje.
> {{remetente}} — Nous Clinical · *responda "sair" pra eu parar.*

### E3 — Credibilidade honesta (sem métrica inventada)
**Assunto:** Por que construímos o Nous do jeito da saúde
> {{primeiro_nome}}, último ângulo. O Nous foi desenhado pro nicho de saúde: **prontuário é dado
> sensível** — restrito a profissional/gestor e **toda edição auditada**. Dados de cada clínica
> isolados; senha com padrão forte. E ajuda embutida no sistema, **sem custo extra**.
> Não prometo número que não posso garantir — posso te mostrar funcionando. Topa 20 min?
> {{remetente}} — Nous Clinical · *responda "sair" e encerro.*

### E4 — Última chamada (educada)
**Assunto:** Encerro o contato com a {{clinica}}?
> {{primeiro_nome}}, este é o último e-mail — não quero virar ruído. Se hoje não é a hora de mexer
> na operação, tudo bem. Quando quiser ver o Nous organizando agenda, prontuário e financeiro num
> lugar só, é só responder uma linha. Obrigado pelo seu tempo, e bom trabalho aí na {{cidade}}.
> {{remetente}} — Nous Clinical · *sem resposta, não escrevo mais.*

### Variações de assunto (A/B)
1. Gestão da {{clinica}} ainda mora numa planilha?
2. {{primeiro_nome}}, uma ideia pra rotina da {{clinica}}
3. Agenda, prontuário e financeiro num lugar só
4. O caixa da {{clinica}} fecha batendo todo dia?
5. 15 minutos sobre a operação da {{clinica}}?
6. Menos gestão, mais cuidado na {{clinica}}
7. Sistema pensado pro consultório pequeno
8. {{primeiro_nome}}, vale uma conversa rápida sobre a {{clinica}}?

### Bump (1 linha)
> {{primeiro_nome}}, só subindo este e-mail: quer que eu mande o link da demo do Nous? Uma linha
> basta. (Responda "sair" se preferir que eu não insista.)

---

## 6. Landing page — o que foi otimizado pra esse funil
A LP (`/` e `/produto`) foi ajustada pra converter tráfego frio em demo:
- **CTA único de conversão:** "Agendar demonstração gratuita" → **WhatsApp** (config `CONTATO_COMERCIAL`).
- **Navbar contextual:** na landing Nous, primário = "Agendar demonstração", secundário discreto
  "Já sou cliente" (login); o "Agendar consulta" (paciente) só aparece no portal `/c/<slug>`.
- **Message match:** H1 nomeia a dor/segmento ("Agenda, prontuário e financeiro numa tela só" /
  "clínicas de 1 a 5 profissionais") + microcommitment ("~20 min, sem compromisso").
- **CTA repetido:** no meio (após as dores) + **barra sticky no mobile** + CTA final.
- **Mobile:** o mock decorativo sai da primeira dobra (H1+CTA primeiro).
- Faixa de transparência (NF-e roadmap etc.) **mantida** — converte no nicho saúde (honestidade).

> **Ação sua:** setar `CONTATO_COMERCIAL` no Render com o **link de WhatsApp** do comercial, ex.:
> `https://wa.me/55DDDNUMERO?text=Quero%20agendar%20a%20demonstra%C3%A7%C3%A3o%20do%20Nous%20Clinical`.
> Sem isso, o CTA de demo não aparece (cai em "Entrar").

---

## 7. As 3 primeiras coisas a fazer
1. **Antes de qualquer disparo:** subdomínio + SPF/DKIM/DMARC no Brevo + warmup (10–20/dia). Sem isso
   tudo vai pro spam.
2. **Setar `CONTATO_COMERCIAL`** (WhatsApp) — destrava o CTA da LP.
3. **Lista qualificada pelo ICP** + assunto por dor. 200 e-mails certos > 2.000 errados (e não queimam
   o domínio).
