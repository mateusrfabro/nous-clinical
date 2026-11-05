---
modulo: papeis
papeis: [recepcao, admin, profissional]
rotas: [/]
---
# Papéis e permissões

O que cada perfil pode fazer no sistema:

## Recepção
- Agenda: marcar, mudar status, check-in, reagendar, lembrete, "Receber".
- Pacientes: cadastrar e editar.
- Financeiro: lançar, receber, contas a receber/pagar (**sem** aluguel/salário/imposto).
- CRM (retornos e aniversariantes) e Cadastro de Itens (convênios/salas/itens).
- **NÃO** acessa: prontuário (LGPD), Relatórios, Auditoria.

## Profissional (quem atende — médico, dentista, psicólogo, fisio…)
- Vê a **própria agenda** e registra o **atendimento** (prontuário).
- Acessa Pacientes **limitado** aos seus (com quem tem agendamento).
- Pode criar **bloqueios** da própria agenda.
- **NÃO** acessa: financeiro, relatórios, cadastro de outros profissionais.

## Admin (dono/gestor da clínica)
- Acessa **tudo** da clínica, incluindo **Relatórios** e **Auditoria**.
- Cadastra profissionais, configura a marca (white-label) e a disponibilidade.

## Superadmin (plataforma)
- Gerencia as clínicas (cross-tenant). Não opera o dia a dia de uma clínica específica.

> Se um menu não aparece para você, provavelmente é de outro perfil. Fale com o
> admin da sua clínica.
