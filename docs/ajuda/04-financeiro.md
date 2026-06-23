---
modulo: financeiro
papeis: [recepcao, admin]
rotas: [/financeiro, /financeiro/novo, /financeiro/contas]
---
# Financeiro

> Acesso de **recepção e admin** (o profissional não vê o financeiro).

## O que é
Controle de **receitas** e **despesas**: fluxo de caixa, contas a receber/pagar e o
recebimento das consultas.

## Fluxo de caixa
A tela inicial do Financeiro mostra o período (dia/semana/mês) com **entradas**,
**saídas** e **saldo**, mais a lista de lançamentos.

## Lançar uma receita ou despesa
1. Clique em **Novo lançamento**.
2. Escolha **tipo** (receita/despesa) e **categoria**.
3. Informe **descrição**, **valor** e (se houver) **vencimento** e **paciente**.
4. Para já marcar como pago, escolha o **status pago** e a **forma de pagamento**.
5. Salve.

> A **forma de pagamento é obrigatória** ao marcar como pago / dar baixa.

## Receber uma consulta
O jeito mais rápido é pela **agenda**: no botão **Receber** da consulta confirmada/
atendida, o sistema cria a receita já ligada àquele agendamento.

## Contas a receber / a pagar
Em **Contas**, veja os lançamentos **pendentes** (a receber e a pagar), com destaque
para os **vencidos**. Use **Pagar / Dar baixa** para quitar (informe a forma de pagamento).

> A recepção **não** vê/lança despesas de **aluguel, salário e imposto** — essas
> categorias são restritas ao admin.
