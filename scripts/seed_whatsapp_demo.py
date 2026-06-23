"""Seed de DEMONSTRACAO da inbox de WhatsApp (so para prints/manual e demo local).

Cria 1 WhatsAppConta para a clinica + 2 conversas com algumas mensagens, para
que as telas de inbox/conversa nao aparecam vazias. Idempotente por
phone_number_id. NAO usar em producao (token e fake).

Uso:  python scripts/seed_whatsapp_demo.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Clinica, Paciente, WhatsAppConta, WhatsAppContato, WhatsAppMensagem,
)
from app.services.cripto import cifrar  # noqa: E402

IN = WhatsAppMensagem.DIRECAO_IN
OUT = WhatsAppMensagem.DIRECAO_OUT


def seed():
    app = create_app("development")
    with app.app_context():
        clinica = Clinica.query.first()
        if not clinica:
            print("Sem clinica — rode scripts/seed.py antes.")
            return

        conta = WhatsAppConta.query.filter_by(clinica_id=clinica.id).first()
        if not conta:
            conta = WhatsAppConta(
                clinica_id=clinica.id,
                phone_number_id="109998887776655",
                waba_id="220011223344556",
                display_phone="+55 43 99888-7766",
                nome_exibicao="Clínica Nous",
                token_cifrado=cifrar("DEMO_TOKEN_FAKE_NAO_FUNCIONA"),
                ativo=True,
            )
            db.session.add(conta)
            db.session.flush()

        if WhatsAppContato.query.filter_by(clinica_id=clinica.id).first():
            print("Inbox demo ja existe — nada a fazer.")
            return

        agora = datetime.now(timezone.utc)
        pac = Paciente.query.filter_by(clinica_id=clinica.id).first()

        # Conversa 1 — paciente conhecido, com nao-lidas
        c1 = WhatsAppContato(
            clinica_id=clinica.id, wa_id="5543999990001",
            nome=(pac.nome_completo if pac else "Maria Oliveira"),
            paciente_id=(pac.id if pac else None),
            nao_lidas=1, ultima_em=agora - timedelta(minutes=4),
        )
        db.session.add(c1)
        db.session.flush()
        msgs1 = [
            (IN,  "Boa tarde! Gostaria de confirmar minha consulta de amanhã.", "lida", agora - timedelta(minutes=40)),
            (OUT, "Olá! Sua consulta está confirmada para amanhã às 14h com a Dra. Ana. 😊", "lida", agora - timedelta(minutes=38)),
            (IN,  "Perfeito, muito obrigada!", "lida", agora - timedelta(minutes=37)),
            (IN,  "Preciso levar algum exame?", "entregue", agora - timedelta(minutes=4)),
        ]
        for d, t, st, ts in msgs1:
            db.session.add(WhatsAppMensagem(
                clinica_id=clinica.id, contato_id=c1.id, direcao=d,
                texto=t, status=(st if d == OUT else None), criado_em=ts))

        # Conversa 2 — número novo, sem paciente vinculado
        c2 = WhatsAppContato(
            clinica_id=clinica.id, wa_id="5543988887777",
            nome="João Pereira", nao_lidas=0,
            ultima_em=agora - timedelta(hours=3),
        )
        db.session.add(c2)
        db.session.flush()
        msgs2 = [
            (IN,  "Olá, vocês atendem o convênio Unimed?", "lida", agora - timedelta(hours=3, minutes=10)),
            (OUT, "Olá! Sim, atendemos Unimed. Quer que eu verifique um horário para você?", "entregue", agora - timedelta(hours=3)),
        ]
        for d, t, st, ts in msgs2:
            db.session.add(WhatsAppMensagem(
                clinica_id=clinica.id, contato_id=c2.id, direcao=d,
                texto=t, status=(st if d == OUT else None), criado_em=ts))

        db.session.commit()
        print("Inbox WhatsApp demo criada (2 conversas).")


if __name__ == "__main__":
    seed()
