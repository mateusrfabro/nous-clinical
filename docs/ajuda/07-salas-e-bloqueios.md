---
modulo: salas-bloqueios
papeis: [recepcao, admin, profissional]
rotas: [/procedimentos, /agenda/bloqueios]
---
# Salas e Bloqueios

## Salas / consultórios
As salas são uma **lista cadastrada** (em *Cadastro de Itens → Sala/consultório*,
recepção/admin). No agendamento você escolhe a sala dessa lista.

> A agenda **impede duas consultas na mesma sala no mesmo horário** — mesmo que
> sejam profissionais diferentes.

## Disponibilidade do profissional
No cadastro do profissional (admin) dá pra definir **dias de atendimento**, **horário
inicial e final** e a **pausa (almoço)**. A agenda e o auto-agendamento geram os
horários livres com base nisso.

## Bloqueios de agenda
Em **Agenda → Bloqueios** você bloqueia períodos em que o profissional não atende
(férias, congresso, reunião, ausência):
1. Escolha o **profissional** (o médico só bloqueia a própria agenda).
2. Informe **data início** e **data fim** (deixe as horas vazias para o dia inteiro)
   **ou** uma **faixa de horário** (ex.: reunião 14:00–16:00).
3. Escolha o **motivo** e salve.

Horários bloqueados não aparecem para agendamento. Para desbloquear, use **Remover**.
Toda criação/remoção de bloqueio fica registrada na auditoria.
