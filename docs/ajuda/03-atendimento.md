---
modulo: atendimento
papeis: [profissional, admin]
rotas: [/agenda/<id>/atendimento, /documentos]
---
# Atendimento / Prontuário

> **Dado sensível (LGPD).** Só o **profissional** (dono da agenda) e o **admin**
> acessam o prontuário. A recepção **não** vê o prontuário.

## Como registrar um atendimento
1. Na agenda, na consulta do paciente, clique em **Atender**.
2. Preencha o prontuário: **Queixa/Anamnese**, **Evolução/Conduta**, **Prescrição**.
3. Se for o caso, marque os **itens/procedimentos** realizados (o valor entra no financeiro).
4. **Retorno recomendado:** escolha 30/90/180/365 dias ou uma data personalizada —
   isso alimenta o painel de retornos do CRM.
5. **Atestado** (opcional): informe os **dias** de afastamento e o **CID**.
6. Clique em **Salvar atendimento**.

> Ao salvar, a consulta vira **status "atendido"** automaticamente.

## Documentos em PDF
Depois de salvar, dá para **exportar a Receita** e o **Atestado** em PDF (com o
logo da clínica). Os botões aparecem na tela do atendimento.

## Anexar exames
Use **Anexar exame** na tela de atendimento para subir um arquivo. O rascunho do
prontuário é preservado ao anexar (você não perde o que digitou).

## Histórico clínico
A tela mostra o histórico de atendimentos do paciente. Por LGPD, o **profissional
vê apenas os atendimentos feitos por ele**; o admin vê todos.

## Por que não consigo mudar para "atendido" na agenda?
"Atendido" não é um status manual — ele vem **somente** do registro do prontuário.
Registre o atendimento e a consulta passa a "atendido" sozinha.
