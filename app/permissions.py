"""Matriz de permissões (RBAC) — degrau para o RBAC granular multi-tenant.

Hoje os papéis (admin/recepcao/profissional) são um enum em `Usuario.tipo`.
Esta matriz traduz cada papel num conjunto de permissões nomeadas (no estilo do
documento de arquitetura do sócio: PATIENT_CREATE, FINANCE_VIEW, ...). Serve a
dois propósitos:

1. **Fonte única e legível** do "quem pode o quê" — documentação executável.
2. Helper `tem_permissao` + global Jinja `pode()` para mostrar/ocultar UI de
   forma consistente com os gates de rota.

Os decorators em `auth_decorators` continuam sendo o **enforcement** de rota;
esta camada é aditiva e prepara a evolução para RBAC tabelado por clínica
(ver `docs/arquitetura/0001-multi-tenant-rbac.md`).
"""

# Permissões — nomes estáveis (usados em templates e, no futuro, em rotas).
PACIENTE_VER = "paciente:ver"
PACIENTE_EDITAR = "paciente:editar"
AGENDA_VER = "agenda:ver"
AGENDA_EDITAR = "agenda:editar"
PRONTUARIO_VER = "prontuario:ver"
EXAME_GERIR = "exame:gerir"
FINANCEIRO_VER = "financeiro:ver"
RELATORIO_VER = "relatorio:ver"
RELATORIO_EXPORTAR = "relatorio:exportar"
PROFISSIONAL_GERIR = "profissional:gerir"
PROCEDIMENTO_GERIR = "procedimento:gerir"

# Recepção: cadastro/agenda/financeiro + cadastro de itens — NUNCA prontuário
# (LGPD) e, por decisão de negócio, SEM relatórios (gestão é do admin).
_RECEPCAO = {
    PACIENTE_VER, PACIENTE_EDITAR, AGENDA_VER, AGENDA_EDITAR,
    FINANCEIRO_VER, PROCEDIMENTO_GERIR,
}
# Profissional: a própria agenda + prontuário/exames dos seus pacientes.
_PROFISSIONAL = {
    PACIENTE_VER, AGENDA_VER, PRONTUARIO_VER, EXAME_GERIR,
}
# Admin: tudo (inclui relatórios, que a recepção não tem mais).
_ADMIN = _RECEPCAO | _PROFISSIONAL | {
    PROFISSIONAL_GERIR, PROCEDIMENTO_GERIR,
    RELATORIO_VER, RELATORIO_EXPORTAR,
}

PERMISSOES_POR_PAPEL = {
    "admin": _ADMIN,
    "recepcao": _RECEPCAO,
    "profissional": _PROFISSIONAL,
}


def permissoes_de(papel: str | None) -> set:
    """Conjunto de permissões de um papel (vazio se papel desconhecido)."""
    return PERMISSOES_POR_PAPEL.get(papel or "", set())


def tem_permissao(usuario, permissao: str) -> bool:
    """True se o usuário autenticado tem a permissão pelo seu papel."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    return permissao in permissoes_de(getattr(usuario, "tipo", None))
