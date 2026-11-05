# Base de ajuda ao usuário — Nous Clinical

> Esta pasta é a **base de conhecimento do chatbot de ajuda** ("Nous Assistente").
> É documentação de **uso do sistema** para a equipe da clínica (recepção, profissional,
> gestora) — diferente de `docs/` (que é técnica, para devs).

## Como escrever (tom e regras)
- **Voz:** direta, no imperativo, na ordem dos cliques reais. "Clique em X", não "o usuário deve clicar".
- **Só o que o sistema faz de verdade.** Se uma afirmação não corresponde a uma regra/rota do código, não entra.
- **Cada tópico** tem frontmatter com `modulo` e `papeis` (quem usa) — o bot usa isso para não explicar função fora do papel do usuário (ex.: prontuário não é para a recepção).
- **Sem dado de paciente.** A doc fala de *como usar*, nunca de registros reais.

## Índice
- [Primeiros passos](00-primeiros-passos.md)
- [Agenda](01-agenda.md)
- [Pacientes](02-pacientes.md)
- [Atendimento / Prontuário](03-atendimento.md)
- [Financeiro](04-financeiro.md)
- [Relatórios](05-relatorios.md)
- [CRM (Retornos e Aniversariantes)](06-crm.md)
- [Salas e Bloqueios](07-salas-e-bloqueios.md)
- [Configurações e marca da clínica](08-configuracoes.md)
- [Papéis e permissões](papeis.md)
- [Perguntas frequentes](faq.md)
- [Glossário](glossario.md)
