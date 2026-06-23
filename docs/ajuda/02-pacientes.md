---
modulo: pacientes
papeis: [recepcao, admin, profissional]
rotas: [/pacientes, /pacientes/novo, /pacientes/<id>]
---
# Pacientes

## O que é
O cadastro dos pacientes da clínica. **Quem cadastra é a recepção ou o admin** — o
médico não cadastra paciente. O profissional vê apenas os pacientes com quem tem
agendamento.

## Como cadastrar um paciente
1. Vá em **Pacientes → Novo paciente** (ou **+ Novo**).
2. Preencha os campos **obrigatórios**: Nome completo, **CPF**, **Data de nascimento**
   e **Telefone/WhatsApp**.
3. Informe a pergunta obrigatória **"Como conheceu a clínica?"** (origem do lead:
   Google, Instagram, Indicação, Site, etc.).
4. Convênio é uma **lista cadastrada** (não dá pra digitar livre — selecione).
5. O endereço pode ser preenchido automaticamente pelo **CEP**.
6. Clique em **Salvar**.

> Se faltar um campo obrigatório (nome, CPF, nascimento, telefone, origem), o
> sistema não salva e mostra o que falta.

## Detalhe do paciente
Na lista, clique no nome do paciente para ver o detalhe: dados, histórico de
consultas e **histórico financeiro** (o que já foi cobrado/recebido).

## Editar
No detalhe ou na lista, use **Editar** para atualizar os dados.

> **Convênio é select, não texto livre** — para aparecer na lista, ele precisa
> estar cadastrado em *Cadastro de Itens → Convênios* (recepção/admin).
