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
