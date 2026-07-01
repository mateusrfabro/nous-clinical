# Checklist do bucket R2 (armazenamento de exames) — ação do sócio

> **✅ AUDITADO EM 2026-07-01 — bucket `nous-clinical` está correto.**
> - Acesso público: **OFF** (sem custom domain, sem public dev URL) — privado.
> - Credencial "R2 Account Token": escopo **mínimo** (`Applied to: nous-clinical`,
>   `Object Read & Write`) — não é admin nem conta-inteira. Nada a trocar.
> - Versioning / Bucket Lock: **deixados desligados de propósito** — reter/travar
>   arquivos conflitaria com a exclusão de exames da **anonimização LGPD**.
> - Lifecycle: regra de abort de multipart já ativa.
> - ⚠️ **Localização: EUA (ENAM)** — transferência internacional; registrar no
>   RIPD/DPA quando formalizar a papelada de LGPD (Cloudflare tem DPA).
>
> _O checklist detalhado abaixo fica como referência._

---


> **Por que isso importa:** os exames dos pacientes (PDFs/imagens) são **dado
> sensível de saúde (LGPD)**. No código, eles já são servidos **só por rota
> autenticada** com checagem de papel (nunca link público). O que falta é
> **auditar a configuração do bucket** no painel da Cloudflare R2 — isso não dá
> pra fazer por código, é config da conta. Leva ~5 minutos.

## O que conferir no painel do Cloudflare R2

- [ ] **Acesso público DESLIGADO.** O bucket **não** pode ter "Public Access" /
      domínio público (`*.r2.dev` ou domínio custom) habilitado. Se estiver
      ligado, qualquer pessoa com a URL do objeto lê o exame. Deixe **privado** —
      o app acessa via credencial (S3 API), não por URL pública.
- [ ] **Object Versioning LIGADO.** Protege contra exclusão acidental e contra
      ransomware/adulteração (mantém versões anteriores dos arquivos).
- [ ] **Lifecycle rule** para expirar versões antigas (ex.: 90 dias) — controla
      custo do versioning sem perder a proteção recente.
- [ ] **Credencial de escopo mínimo.** A `S3_ACCESS_KEY_ID` que o app usa deve
      ter permissão **só neste bucket**, não na conta inteira. Se hoje é uma
      chave de conta, crie um token de bucket específico e troque a env.
- [ ] **Região / jurisdição.** Confirmar onde o bucket está hospedado (para o
      DPA/RIPD de LGPD: dado de saúde brasileiro). R2 permite escolher
      jurisdição — idealmente uma compatível com a operação no Brasil.

## O que já está resolvido no código (não precisa mexer)

- Exames servidos **só** por `GET /exames/<id>/download` autenticado, com
  checagem de papel (clínico) e escopo de clínica — nunca URL direta/pública.
- Exclusão de exame apaga o **arquivo antes** do registro (sem órfão) e a
  **anonimização LGPD** apaga os arquivos do paciente do storage.
- Content-Type derivado da extensão validada no servidor (anti-contrabando de
  HTML same-origin).

> Depois de marcar os itens acima, avise que eu registro no changelog do sócio
> que a auditoria do bucket foi concluída.
