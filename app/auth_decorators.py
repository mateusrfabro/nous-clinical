"""Decorators centralizados pra protecao de rotas por papel.

Papeis do sistema:
- admin       — dono/gestor da clinica. Acessa tudo.
- profissional — medico/profissional de saude. Ve a propria agenda + pacientes
                 que atende. Vinculado a um registro Profissional.
- recepcao    — recepcionista. Agenda consultas e gerencia pacientes, mas nao
                 acessa prontuario clinico (dado sensivel).
"""
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def role_required(*roles: str, check_cadastro: bool = False):
    """Exige current_user com um dos papeis informados.

    Args:
        *roles: "admin" | "profissional" | "recepcao".
        check_cadastro: se True e o papel for profissional, exige registro
            Profissional vinculado (cadastro completo).
    """
    mensagens = {
        "admin":        "Acesso restrito a administradores.",
        "profissional": "Esta área é apenas para profissionais.",
        "recepcao":     "Esta área é apenas para a recepção.",
    }

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or current_user.tipo not in roles:
                msg = mensagens.get(roles[0], "Acesso restrito.")
                flash(msg, "error")
                return redirect(url_for("main.dashboard"))
            if check_cadastro and current_user.tipo == "profissional":
                if not current_user.profissional:
                    flash("Complete seu cadastro de profissional primeiro.", "error")
                    return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# Atalhos pros papeis mais comuns
admin_required        = role_required("admin")
profissional_required = role_required("profissional", check_cadastro=True)
# Recepcao OU admin gerenciam pacientes e agenda.
recepcao_ou_admin     = role_required("recepcao", "admin")
# Quem pode ver/editar prontuario: profissional (o seu) ou admin.
clinico_required      = role_required("profissional", "admin")