"""Comandos de CLI (flask <cmd>). Disparáveis por cron do sistema/PaaS."""
import click
from flask.cli import with_appcontext


def register_commands(app):
    @app.cli.command("lembretes")
    @click.option("--data", "data", default=None,
                  help="Dia alvo YYYY-MM-DD (default: amanhã, fuso BR).")
    @with_appcontext
    def lembretes_cmd(data):
        """Envia lembretes das consultas do dia-alvo (idempotente)."""
        from datetime import datetime
        from app.services.lembretes import enviar_lembretes
        alvo = datetime.strptime(data, "%Y-%m-%d").date() if data else None
        resumo = enviar_lembretes(alvo)
        click.echo(
            f"Lembretes {resumo['alvo']}: {resumo['enviados']} enviado(s), "
            f"{resumo['sem_canal']} sem canal, {resumo['falhas']} falha(s) "
            f"de {resumo['total']} consulta(s)."
        )

    @app.cli.command("criar-superadmin")
    @click.option("--email", required=True)
    @click.option("--senha", required=True)
    @click.option("--nome", default="Super Admin")
    @with_appcontext
    def criar_superadmin_cmd(email, senha, nome):
        """Cria o superadmin da plataforma (cross-tenant, sem clínica)."""
        from app import db
        from app.models import Usuario
        from app.services.passwords import hash_senha
        email = email.strip().lower()
        if Usuario.query.filter_by(email=email).first():
            click.echo(f"Já existe usuário com e-mail {email}.")
            return
        if len(senha) < 8:
            click.echo("Senha precisa de ao menos 8 caracteres.")
            return
        u = Usuario(email=email, senha_hash=hash_senha(senha),
                    nome_responsavel=nome, tipo="superadmin", clinica_id=None)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Superadmin {email} criado.")
