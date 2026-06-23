---
modulo: configuracoes
papeis: [admin]
rotas: [/configuracoes/aparencia, /profissionais, /procedimentos]
---
# Configurações e marca da clínica

> Acesso do **admin/gestora**.

## Aparência / white-label
Em **Configurações → Aparência** a clínica define sua identidade:
- **Logo** (aparece no sistema e nos PDFs de receita/atestado).
- **Tema/cor** da marca.
- **Slug** e **QR de agendamento** para o portal público.

A mudança vale **ao salvar** (a última ação prevalece).

## Profissionais
Em **Profissionais** o admin cadastra os médicos. Ao cadastrar, o sistema **cria o
login** do profissional junto. Defina especialidade, registro, cor na agenda,
duração padrão, comissão, sala padrão e a **disponibilidade** (dias/horários/pausa).

## Cadastro de Itens (recepção/admin)
Em **Cadastro de Itens** ficam três listas controladas:
- **Itens faturáveis** (procedimentos com valor, e preço por convênio).
- **Convênios** (a lista que aparece nos selects de convênio).
- **Salas / consultórios** (a lista usada no agendamento).
