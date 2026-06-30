# Nous Clinical — Material Comercial

> **Menos gestão. Mais medicina.**
>
> Documento de apoio à venda. Uso do sócio comercial e, em seguida, de donos e
> gestores de clínica. Tom honesto: o que está pronto é apresentado como pronto; o
> que é opcional ou roadmap está **marcado como tal**. Nada de promessa que o produto
> não cumpre.

---

## 1. O pitch

O **Nous Clinical** é o sistema que organiza a clínica de ponta a ponta — agenda,
pacientes, prontuário, financeiro e relatórios — em um só lugar, com inteligência
clínica e o nível de proteção de dados que a saúde exige (LGPD). A recepção agenda e
recebe, o profissional registra o atendimento e emite receita/atestado, o gestor
acompanha faturamento e ocupação em tempo real. A ideia cabe no slogan: a clínica
gasta **menos tempo com gestão** e sobra **mais tempo para medicina**.

- **Tudo num lugar só, com cada um vendo o que é seu.** Recepção, profissional e
  gestor têm telas próprias. Menos clique, menos erro, e o prontuário fica restrito a
  quem pode ver (exigência de LGPD, não um detalhe).
- **Decisão com número, não com achismo.** Faturamento por médico, taxa de faltas,
  ocupação, ticket médio, dependência de convênio, risco de evasão de paciente — tudo
  em relatórios prontos e exportáveis.
- **Cresce com a clínica.** Multi-clínica com marca própria (white-label), WhatsApp,
  conciliação bancária, portal de agendamento online e nota fiscal NFS-e — recursos
  que se **ligam quando a clínica quiser**, sem trocar de sistema.

---

## 2. Para quem é

Clínicas e consultórios médicos (e demais profissionais de saúde) que querem sair da
planilha/agenda de papel e profissionalizar a operação sem virar reféns de TI. O
sistema é desenhado em torno de **três perfis de uso**, cada um com sua tela:

| Perfil | Quem é | O que ganha |
|---|---|---|
| **Recepção** | Recepcionista / secretária | Agenda, cadastra paciente, faz check-in e recebe pagamento — fluxo rápido do balcão, sem acesso a dado sensível que não precisa ver. |
| **Profissional** | Médico(a) e demais profissionais de saúde | Vê **só a própria agenda**, registra o prontuário e emite receita/atestado em PDF. Menos distração, foco no atendimento. |
| **Gestor / Dono (Administrador)** | Quem toca o negócio | Visão completa: financeiro, relatórios, auditoria, cadastros e personalização da marca. Enxerga a clínica inteira em uma tela. |

> Há ainda o perfil **superadmin** (da plataforma/operadora) para administrar várias
> clínicas — relevante no modelo white-label, ver seção 7.

---

## 3. Módulos e funcionalidades

Para cada módulo: **o que faz** + **o benefício de negócio**.

### Agenda
- **O que faz:** quatro formas de ver o dia — **lista**, **semana**, **grade por
  horário** e **Quadro (Kanban)** com **arrastar** o paciente entre etapas
  (agendado → confirmado → atendido). Tem **bloqueios** de horário (folga, almoço,
  feriado) e **trava de conflito**: o sistema **não deixa marcar dois pacientes no
  mesmo horário com o mesmo profissional ou na mesma sala**.
- **Benefício:** acaba a dor de agenda dupla e furo de sala. A recepção trabalha do
  jeito que prefere (lista ou quadro) e o dia "anda" sozinho na tela.

### Pacientes
- **O que faz:** cadastro completo (dados, contato, endereço por CEP, convênio,
  observações) com histórico de consultas e financeiro do paciente reunidos.
- **Benefício:** a ficha do paciente vira fonte única; ninguém procura dado em três
  cadernos.

### Prontuário / Atendimento
- **O que faz:** o profissional registra queixa, evolução e prescrição; gera
  **receita e atestado em PDF** com a marca da clínica; **anexa exames**; e marca o
  **retorno recomendado**. Toda edição de prontuário fica **registrada (auditada)**.
- **Benefício:** documento clínico padronizado e profissional, com rastreabilidade —
  proteção da clínica e do paciente. Dado sensível, tratado como tal.

### Painel do Gestor
- **O que faz:** indicadores do dia logo na entrada — **faturamento de hoje**, **entrada
  da semana**, **taxa de faltas**, **a receber em atraso** e **ocupação** por profissional
  (além de consultas do dia, pacientes e profissionais ativos).
- **Benefício:** o dono abre o sistema e em segundos sabe como está o dia, sem pedir
  relatório a ninguém.

### Financeiro
- **O que faz:** **fluxo de caixa**, **contas a receber e a pagar**, recebimento da
  consulta integrado à agenda, **conciliação bancária** importando o extrato do banco
  por **OFX ou CSV** (concilia automático o que bate e aponta divergências), e
  **fechamento de caixa diário** (abrir/fechar/reabrir o caixa do dia).
- **Benefício:** o dinheiro da clínica fica conferido e fechado todo dia, com o
  extrato do banco batendo com o sistema. Menos vazamento, menos surpresa no fim do mês.

> **Repasse médico (comissão):** o sistema calcula o **repasse por profissional** sobre
> a receita recebida, usando o percentual de comissão de cada um. Hoje esse cálculo
> aparece **nos Relatórios** (ver abaixo), pronto para fechar o repasse do período.

### Relatórios / BI
- **O que faz:** indicadores do período prontos e exportáveis em CSV — **faturamento e
  receita por médico**, **repasse/comissão por profissional**, **dependência de
  convênio**, **produtividade e ocupação por profissional**, **ticket médio por
  paciente**, **faixa etária**, **origem dos leads**, **DRE** (receitas x despesas) e
  **pacientes em risco de evasão** (que não voltam há tempo).
- **Benefício:** o gestor decide com dado: de qual convênio dependo demais? qual médico
  produz mais? quem está prestes a sumir? Tudo já calculado.

### CRM
- **O que faz:** painel de **retornos** recomendados pendentes e de **aniversariantes**
  para a clínica se relacionar com o paciente. Inclui **lembrete de consulta
  automático** por **WhatsApp / e-mail**.
- **Benefício:** paciente que volta vale mais que paciente novo. O CRM transforma o
  "ele sumiu" em uma lista de quem chamar de volta hoje.
  > **Importante (honesto):** o lembrete por **WhatsApp** depende de a clínica conectar
  > o número e ter um **template de mensagem aprovado pela Meta**; o lembrete por
  > **e-mail** depende do envio de e-mail configurado. Não é "liga e dispara" no primeiro
  > minuto — exige esse preparo inicial.

### WhatsApp Business integrado *(opcional — liga quando quiser)*
- **O que faz:** cada clínica conecta o **próprio número** de WhatsApp Business e
  conversa com o paciente de dentro do sistema. O token de acesso fica **cifrado**.
- **Benefício:** atendimento no canal que o paciente já usa, sem sair da ferramenta.
  > **Honesto:** o recurso vem **inerte** (desligado) até a clínica conectar o número;
  > o **custo das mensagens é da clínica, pago à Meta**.

### Agendamento online (Portal do paciente) *(opcional)*
- **O que faz:** um link público com a marca da clínica onde o **paciente agenda
  sozinho** (e confirma a consulta). Inclui QR Code para divulgar.
- **Benefício:** menos telefone tocando na recepção; agenda preenchendo fora do horário
  comercial.

### Nota Fiscal de Serviço (NFS-e) *(parcial — ver status)*
- **O que faz:** configuração do **emitente por clínica** (CNPJ, regime, ISS, inscrição
  municipal, código de serviço) integrada a um emissor nacional (Nuvem Fiscal).
- **Benefício:** caminho para emitir a nota da consulta sem sair do sistema.
  > **Honesto — não prometer emissão ainda:** a **Fase 1 (cadastro/configuração) está
  > pronta**, mas a **emissão da nota (Fase 2) ainda não está liberada** — ela depende
  > de **certificado digital A1 (e-CNPJ)**, exigido pelo emissor já em ambiente de
  > teste. Até lá, o módulo fica **desligado** e não aparece no menu. Ver seção 6.

### Suporte Nous (ajuda dentro do sistema)
- **O que faz:** assistente de ajuda embutido que busca na base de manuais por papel —
  **custo zero, sempre ligado** para a equipe. Há um modo com **IA opcional**.
- **Benefício:** a equipe tira dúvida de uso sem abrir chamado nem ligar pro suporte —
  reduz fricção na adoção. A ajuda padrão **não tem custo** porque não usa IA.
  > **Honesto:** o **modo IA é opcional e vem desligado**; quando ligado, tem custo de
  > centavos por uso (arcado pela operadora, não pela clínica).

### Auditoria / LGPD
- **O que faz:** trilha de auditoria das ações sensíveis (ex.: edição de prontuário),
  consultável e exportável pelo administrador.
- **Benefício:** a clínica sabe **quem fez o quê e quando** — proteção jurídica e
  conformidade com LGPD.

### Multi-clínica + White-label
- **O que faz:** uma instalação atende **várias clínicas isoladas** entre si; cada uma
  com **logo, cor e link próprios** (marca da clínica, não do fornecedor).
- **Benefício:** permite operar uma rede ou revender o sistema com a marca do cliente.
  Ver seção 7.

---

## 4. Diferenciais competitivos

O que coloca o Nous à frente de boa parte dos concorrentes de nicho:

- **Inteligência clínica de verdade no fluxo** — retorno recomendado, risco de evasão e
  produtividade não são telas soltas: nascem do atendimento e viram ação no CRM.
- **Multi-tenant com white-label** — vários clientes isolados, cada um com sua marca.
  Pronto para rede de clínicas ou revenda.
- **LGPD by design** — prontuário é dado sensível **restrito por papel** e **toda edição
  é auditada**. Não é um "módulo de segurança" colado depois; está na arquitetura.
- **WhatsApp nativo** — conversa com o paciente sem ferramenta paralela (opcional).
- **Conciliação bancária (OFX/CSV) + fechamento de caixa diário** — controle financeiro
  que muitos sistemas de clínica simplesmente não têm.
- **Portal de agendamento online** com a marca da clínica.
- **Caminho para NFS-e** integrado ao mesmo sistema (Fase 1 pronta; ver status).
- **Suporte embutido de custo zero** — adoção mais fácil, sem custo recorrente de ajuda.

---

## 5. Segurança e conformidade (em linguagem de negócio)

- **Cada clínica é uma ilha.** Os dados de uma clínica **não se misturam** com os de
  outra — o isolamento é automático no sistema (multi-tenant por clínica).
- **Cada um vê só o que pode.** O prontuário, por ser dado sensível de saúde, fica
  **restrito ao profissional e ao administrador**; a recepção não acessa. Isso atende à
  LGPD e reduz risco de vazamento interno.
- **Senha guardada do jeito certo.** As senhas são protegidas com **Argon2id** (padrão
  forte atual), nunca guardadas em texto.
- **Rastro de auditoria.** Ações sensíveis ficam registradas com **quem, o quê e
  quando**, exportável pelo gestor — proteção jurídica da clínica.
- **Segredos fora do código.** Credenciais e tokens (ex.: WhatsApp) ficam **cifrados /
  em variáveis de ambiente**, nunca expostos.
- **Qualidade verificada.** O produto roda uma suíte de testes automatizada ampla e
  passou por **auditoria de segurança** (incluindo revisão adversarial dos módulos mais
  novos).

---

## 6. Status de maturidade (tabela honesta)

Classificação:
**Pronto** = no ar e em uso · **Opcional** = pronto, vem desligado, liga quando a
clínica quiser · **Parcial / Roadmap** = depende de uma etapa ou ainda em construção.

| Recurso | Status | Observação honesta |
|---|---|---|
| Agenda (4 visões, Kanban, bloqueios, trava de conflito) | ✅ Pronto | — |
| Pacientes | ✅ Pronto | — |
| Prontuário, receita/atestado em PDF, anexo de exame, retorno | ✅ Pronto | Exame anexado persiste (armazenamento em nuvem ativo). |
| Painel do gestor (faturamento, faltas, ocupação) | ✅ Pronto | — |
| Financeiro: fluxo de caixa, contas a pagar/receber | ✅ Pronto | — |
| Conciliação bancária (OFX/CSV) | ✅ Pronto | — |
| Fechamento de caixa diário | ✅ Pronto | — |
| Repasse médico (comissão) | ✅ Pronto | Calculado nos Relatórios, por profissional. |
| Relatórios / BI (faturamento por médico, convênio, produtividade, ticket, faixa etária, leads, DRE, evasão) | ✅ Pronto | Exportação em CSV. |
| CRM (retornos, aniversariantes) | ✅ Pronto | — |
| Lembrete de consulta automático (WhatsApp/e-mail) | ⚙️ Opcional | WhatsApp exige número conectado + **template aprovado pela Meta**; e-mail exige envio configurado. |
| WhatsApp Business integrado | ⚙️ Opcional | Vem inerte; clínica conecta o número; **mensagens pagas pela clínica à Meta**. |
| Suporte Nous (ajuda) | ✅ Pronto | **Custo zero**, sempre ligado. |
| Suporte com IA | ⚙️ Opcional | **Desligado por padrão**; centavos/uso (operadora) quando ligado. |
| Agendamento online (portal do paciente) | ✅ Pronto | Link + QR com a marca da clínica. |
| Auditoria / LGPD | ✅ Pronto | — |
| Multi-clínica + white-label | ✅ Pronto | — |
| **NFS-e — Fase 1 (config do emitente)** | ✅ Pronto (desligado) | Não aparece no menu até ser ligado. |
| **NFS-e — Fase 2 (emissão da nota)** | ⛔ Roadmap | **Bloqueada até termos certificado A1 de teste**; emissão ainda não pode ser prometida. Quando lançar, cada clínica precisa de A1, inscrição municipal, regime, ISS e código de serviço. |

> **Em uma frase, honesta:** o núcleo de gestão (agenda, pacientes, prontuário,
> financeiro com conciliação e fechamento, relatórios, CRM, portal, auditoria,
> white-label) está **pronto e em produção**. WhatsApp e IA são **opcionais**, ligam
> quando a clínica quiser. A **emissão de nota fiscal ainda não está liberada** — não
> deve ser vendida como pronta.

---

## 7. Modelo de entrega

- **SaaS na nuvem.** A clínica acessa pelo navegador; nada para instalar. A equipe que
  sabe usar WhatsApp e e-mail consegue usar o Nous.
- **Multi-clínica e white-label.** Uma instalação serve **várias clínicas isoladas**,
  cada uma com **logo, cor e link próprios** — modelo ideal para rede ou para revenda
  com a marca do cliente.
- **Atualização contínua.** Melhorias e correções entram automaticamente; recursos novos
  sobem **desligados/seguros** e só "acendem" quando alguém liga — sem sustos para quem
  já está usando.
- **Recursos que ligam por clínica.** WhatsApp, IA de suporte e (futuramente) NFS-e são
  ativados conforme a clínica quiser, sem trocar de sistema.
- **Investimento:** **valores sob consulta / a definir** com o sócio comercial. Vale
  alinhar que alguns recursos têm **custo de terceiros** repassado de forma transparente:
  WhatsApp (Meta, pago pela clínica) e, no futuro, a mensalidade do emissor de NFS-e.

---

> **Princípio deste material:** vender o que entrega. O Nous Clinical já resolve a gestão
> da clínica hoje; os itens marcados como opcionais e de roadmap devem ser apresentados
> exatamente assim — como caminho, não como promessa cumprida.
