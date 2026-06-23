<!-- GUIA DE ESTILO DO MANUAL DO USUÁRIO — leia antes de escrever qualquer capítulo. -->

# Guia de estilo — Manual do Usuário Nous Clinical

Público: **pessoas leigas** da clínica (recepcionista, médico, gestor). Não são
técnicas. Escreva como se explicasse para alguém no primeiro dia de trabalho.

## Voz e tom
- Português do Brasil, **você** (informal, acolhedor). Frases curtas.
- Zero jargão técnico. Nada de "endpoint", "rota", "POST", "model", "tenant".
  Diga "tela", "botão", "campo", "lista", "clínica".
- Explique **o porquê** quando ajuda ("isso evita marcar duas consultas na mesma
  sala"), não só o passo.

## Formato de cada capítulo
1. Comece com um título `# <Módulo>` e uma linha dizendo **para que serve** e
   **quem usa** (qual papel).
2. Para cada tela/ação, use **passos numerados** curtos ("1. Clique em **Novo**.").
3. Nomes de botões/campos em **negrito**, exatamente como aparecem na tela.
4. Inclua a imagem da tela logo após apresentá-la, com legenda:
   `![Legenda curta](assets/NOME.png)`
   (os arquivos já existem em `docs/manual/assets/`).
5. Use caixas de aviso quando fizer sentido:
   - `> 💡 **Dica:** ...`  (atalho/boa prática)
   - `> ⚠️ **Atenção:** ...` (erro comum, dado sensível, irreversível)
   - `> 🔒 **Quem acessa:** ...` (qual papel vê/faz aquilo)
6. Termine com **"Perguntas rápidas"** (2-4 Q&A do tipo FAQ) quando couber.

## Regras de conteúdo
- **Seja exato com os rótulos**: abra o template/tela real e use os textos que
  aparecem de fato (não invente nomes de botão).
- Quando uma ação for restrita por papel, **diga isso** (ex.: "Só o **administrador**
  vê esta tela"; "A **recepção** não vê despesas de aluguel/salário/imposto").
- Não prometa o que o sistema não faz. Se algo é "em breve", não documente como pronto.
- Não exponha detalhes de segurança/implementação (cifragem, HMAC, etc.) — isso é
  do manual técnico, não do usuário.

## Papéis (use estes nomes)
- **Administrador** (dono/gestor da clínica) — vê tudo da clínica.
- **Recepção** — agenda, pacientes, financeiro, cadastros. Não vê prontuário nem relatórios.
- **Profissional** (médico) — própria agenda, atendimento/prontuário, seus pacientes.
- (**Superadmin** é uso interno da PGS — não citar no manual do cliente.)

## Marca
- O produto é **Nous Clinical** — "Menos gestão. Mais medicina."
- Cores podem mudar por clínica (white-label), então **não** diga "o botão verde";
  diga "o botão **Salvar**".
