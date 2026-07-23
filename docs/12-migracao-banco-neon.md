# 12 — Migração do banco: Render Postgres (free) → Neon (free)

**Por quê:** o Postgres *free* do Render **expira em 30 dias + 14 de carência e apaga
tudo, sem backup**. O **Neon free** é Postgres de verdade (PG17), **não apaga nem
pausa por inatividade** e tem custo zero. Nosso código roda nele sem adaptação (a
auditoria confirmou: nenhuma extensão, o único recurso "especial" é o índice único
parcial anti-double-book, que o Neon suporta). Use **Postgres 18** no Neon (o
banco do Render também era 18) — mantém as ferramentas de dump/restore alinhadas.

> ⚠️ **Antes de tudo:** veja no dashboard do Render → banco `nous-clinical-db` → o
> **status** e a **data de expiração**. Se aparecer *expired/suspended*, os dados
> podem já ter sido perdidos (o free do Render não tem backup) — nesse caso a
> migração vira "começar limpo" (Parte C-2). Se ainda estiver no ar, migre **agora**.

---

## Parte A — Criar a conta e o projeto no Neon
1. Acesse **https://neon.com** → **Sign up** (login com GitHub ou Google; grátis, **sem cartão**).
2. **Create project**:
   - **Name:** `nous-clinical`
   - **Postgres version:** `18`
   - **Region:** escolha a **mesma região do seu web no Render** — hoje é **Oregon**,
     então selecione **AWS US West (Oregon) — us-west-2**.
     > Por quê Oregon e não São Paulo? O app faz **dezenas de queries por página**;
     > o que pesa é a latência **app↔banco**. Banco longe do app deixa cada tela
     > lenta. O browser↔app já é ~150ms do Brasil de qualquer jeito (o Render não
     > tem região no Brasil), então co-locar banco+app é o que importa. Se um dia
     > mover o web pra outra região, mova o banco junto.
3. **Create project**.

## Parte B — Pegar a connection string (do POOLER)
1. No projeto → **Connect** / **Connection Details**.
2. Marque **"Pooled connection"** (o host termina em **`-pooler`**).
3. Copie a string. Formato:
   ```
   postgresql://USER:PASSWORD@ep-xxxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Guarde essa string — vai no Render (`DATABASE_URL`) e no backup.
   > Sempre a do **pooler**: o free tem cap baixo de conexões diretas; nosso app
   > abre até ~16 (2 workers × pool 3 + overflow 5). E `?sslmode=require` é obrigatório.

## Parte C — Levar schema + dados

### C-1 — Banco do Render ainda tem os dados (migrar)
Precisa do `pg_dump`/`pg_restore` **do PostgreSQL 18** (ou use o Docker abaixo).
```bash
export OLD="postgresql://...render..."                          # Render: "External Connection String"
export NEW="postgresql://...neon...-pooler...?sslmode=require"  # Neon (Parte B)

pg_dump "$OLD" -Fc -f nous.dump                                 # 1) dump do Render
pg_restore -d "$NEW" --no-owner --no-privileges nous.dump       # 2) restaura no Neon
```
`--no-owner --no-privileges`: o usuário do Neon difere do Render; evita erro de dono.

Sem o client 17 local? Use Docker:
```bash
docker run --rm -v "$PWD":/b -w /b postgres:18 bash -c '
  pg_dump "'"$OLD"'" -Fc -f nous.dump &&
  pg_restore -d "'"$NEW"'" --no-owner --no-privileges nous.dump'
```

### C-2 — Banco do Render já expirou (começar limpo)
Não há o que dumpar. O schema é criado sozinho no 1º deploy (`entrypoint.sh` roda
`flask db upgrade`). Depois crie o superadmin (Parte E-2). Os dados antigos foram
perdidos — por isso a Parte F (backup) passa a ser obrigatória.

## Parte D — Apontar o Render pro Neon
1. Faça deploy do commit que altera o `render.yaml` (o `DATABASE_URL` vira secret).
   Se o Render pedir para **re-sincronizar o Blueprint**, aceite.
2. Render → serviço **nous-clinical** → **Environment** → variável **`DATABASE_URL`**
   → cole a string do **pooler** do Neon (Parte B) → **Save**.
   > ⚠️ Se `DATABASE_URL` ficar **vazia**, o app sobe em **SQLite efêmero** e perde
   > os dados a cada deploy. Preencha **antes** do deploy.
3. **Manual Deploy** (ou aguarde o autoDeploy). Nos **Logs** deve aparecer
   `[nous] Aplicando migrations...` sem erro e o gunicorn iniciando.

## Parte E — Verificar
1. Abra **https://nousclinical.com** e faça login.
2. **C-1:** seus dados estão lá. **C-2:** banco limpo → faça E-2.

### E-2 — Criar o superadmin (só no cenário "começar limpo")
Render → serviço → **Shell** (ou local, com `DATABASE_URL` do Neon):
```bash
flask criar-superadmin --email super@nous.com --senha "UMA_SENHA_FORTE" --nome "Super Admin"
```
Troque a senha. Depois cadastre clínicas/usuários normalmente pela interface.

## Parte F — Backup automático (não pule)
Já existe o workflow **`.github/workflows/backup-db.yml`** (dump diário cifrado →
R2/B2). Ele fica inerte até você configurar os secrets:
1. **Gere um par de chaves age** (no PC): `age-keygen -o backup-key.txt`.
   Guarde `backup-key.txt` **fora do git** (é a chave que **descriptografa**).
   Copie a linha `# public key: age1...`.
2. **Bucket S3-compatível grátis:** Cloudflare **R2** (10 GB) ou Backblaze **B2**
   (10 GB). Anote **endpoint**, **access key**, **secret**, **nome do bucket**.
3. GitHub → repositório → **Settings → Secrets and variables → Actions** → crie:
   - `DATABASE_URL` = string do pooler do Neon
   - `BACKUP_AGE_PUBKEY` = a public key `age1...`
   - `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_BUCKET`
4. **Rode uma vez manualmente:** Actions → **backup-db** → *Run workflow*. Confirme
   o arquivo `nous-*.dump.age` no bucket.
5. **Teste de restore (1×/trimestre):** baixe o último e
   `age -d -i backup-key.txt nous-*.dump.age | pg_restore -d "URL_DE_TESTE"`, depois
   confira `SELECT count(*)` em `pacientes`, `agendamentos`, `lancamentos`.
   *Backup não testado = sem backup.*

## Parte G — Limpeza
- Com tudo verde: Render → **delete o banco `nous-clinical-db` antigo** (não é mais
  usado; ia expirar mesmo).
- Deixe `RUN_SEED=false` e `RUN_DEMO=false`.

---

## Notas
- **Web continua no plano free** (custo zero) → ainda "dorme" após 15 min ocioso
  (cold start ~30-60s). Isso **não é perda de dado**. Se a lentidão incomodar, web
  `starter` (~US$7/mês) tira o sono.
- `postgres://` vs `postgresql://`: o `config.py` já normaliza — ambos funcionam.
- **Teto do Neon free:** 0,5 GB storage + 100 compute-hours/mês. Se estourar, o
  *compute* suspende até o próximo ciclo (o **dado fica intacto**, mas o app cai) —
  esse é o gatilho natural para migrar ao Neon pago (~US$5-19/mês, pay-as-you-go)
  quando houver clínica pagante.
