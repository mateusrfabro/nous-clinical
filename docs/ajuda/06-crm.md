---
modulo: crm
papeis: [recepcao, admin]
rotas: [/crm/retornos, /crm/aniversariantes]
---
# CRM — Retornos e Aniversariantes

> Acesso de **recepção e admin**. Há duas abas: **Retornos** e **Aniversariantes**.

## Retornos
Lista os pacientes cujo **retorno recomendado** pelo médico (no atendimento) está
vencendo/vencido e que **ainda não reagendaram**. Para cada um:
- **Agendar retorno** (vai direto pro agendamento já com o paciente).
- **Gerar mensagem** — rascunho de retorno que você revisa e envia pelo WhatsApp (ver abaixo).

Use os filtros de janela (vencidos, até 30/60/90/180 dias).

> O paciente "sai" da lista de retornos quando se consulta de novo. Para voltar, o
> médico precisa marcar um novo retorno no próximo atendimento.

### Gerar mensagem (Concierge)
O botão **Gerar mensagem** monta um **rascunho** de mensagem de retorno no nome do paciente
(**sem custo**). Você revisa/edita, clica em **Abrir WhatsApp** (envia com o texto aprovado) ou
**Copiar**; **Gerar de novo** traz outra versão. A ferramenta **sugere, não envia** — nada sai
sem você revisar. Ela **não lê o prontuário** (só nome, profissional e tempo desde a última
consulta). O mesmo botão aparece no relatório **Pacientes em risco de evasão**.

## Aniversariantes
Mostra os **aniversariantes do dia**: nome, idade, telefone, botão **WhatsApp** (com
mensagem de parabéns pronta) e **Registrar contato** (grava na auditoria que a
clínica felicitou). Ótimo para a recepção fazer o relacionamento.
