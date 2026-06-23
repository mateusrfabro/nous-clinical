---
modulo: agenda
papeis: [recepcao, admin, profissional]
rotas: [/agenda, /agenda/novo, /agenda/semana, /agenda/grade, /agenda/bloqueios]
---
# Agenda

## O que é
A agenda mostra as consultas do dia. A recepção marca e organiza; o profissional
vê a própria agenda e atende.

## Visualizações
No topo da agenda há um seletor: **Dia** (lista), **Grade** (grade visual de horários
estilo calendário) e **Semana** (grade de segunda a domingo). Use as setas
**Anterior / Próximo** ou **Hoje** para navegar.

## Como agendar uma consulta
1. Clique em **+ Agendar consulta**.
2. Escolha o **paciente**, o **profissional**, o **dia** e a **hora**.
3. Escolha a **duração** (30/60/90/120 min) — o padrão vem do profissional.
4. Selecione a **sala** (lista cadastrada) e o **convênio**, se houver.
5. Clique em **Salvar**.

> O sistema **bloqueia conflito de horário** do mesmo profissional e **conflito de
> sala** (duas consultas na mesma sala no mesmo horário). Também não deixa agendar
> em **data passada**.

## Status da consulta
`agendado → confirmado → atendido` (ou `cancelado` / `faltou`).
- A recepção muda o status no seletor da linha (agendado/confirmado/cancelado/faltou).
- **"Atendido" não é manual** — ele só aparece quando o profissional registra o
  prontuário. Por isso você não consegue marcar "atendido" na mão.

## Check-in (chegada do paciente)
Quando o paciente chega, clique em **Check-in** na linha dele. Isso registra o
horário de chegada e confirma a presença (agendado → confirmado). Clicar de novo
desfaz o check-in.

## Reagendar
Clique em **Editar** na consulta, troque profissional/dia/hora e salve. Não é
possível reagendar uma consulta **já atendida**.

## Lembrete por WhatsApp
Na linha da consulta há o botão **Lembrete**, que abre o WhatsApp com uma mensagem
pronta e um link de confirmação para o paciente.

## Receber o pagamento da consulta
Em consultas confirmadas/atendidas aparece o botão **Receber** (recepção/admin),
que cria a receita no financeiro ligada àquela consulta.
