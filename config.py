import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base. SECRET_KEY tem fallback aleatorio aqui (overridable por subclasses)."""
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    # Render/Heroku entregam a URL como 'postgres://'; o SQLAlchemy 2.0 exige
    # 'postgresql://'. Normaliza pra funcionar em qualquer provedor.
    _db_url = os.getenv("DATABASE_URL", "sqlite:///nous.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Limite de upload (exames, documentos do paciente).
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Storage de arquivos (logo, exames). "local" (disco) ou "s3" (R2/S3/B2).
    # Em PaaS de disco efêmero (Render), use s3 — senão os arquivos somem no
    # redeploy/spin-down. Veja docs/06-deploy.md.
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")   # R2: https://<acc>.r2.cloudflarestorage.com
    S3_BUCKET = os.getenv("S3_BUCKET", "")
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_REGION = os.getenv("S3_REGION", "auto")

    # Username do bot Telegram (deep link t.me/<username>?start=...).
    # Canal opcional pra lembrete de consulta + reset de senha.
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "nousclinicalbot")
    TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
    # Numero WhatsApp publico pra contato pre-cadastro. So digitos com codigo
    # pais (ex: 5543999999999). Vazio = botao flutuante nao aparece.
    WHATSAPP_NUMERO = os.getenv("WHATSAPP_NUMERO", "")

    # Token do endpoint de tarefas agendadas (POST /tarefas/lembretes). Vazio =
    # endpoint desabilitado. Defina e use no cron/gatilho externo.
    TAREFAS_TOKEN = os.getenv("TAREFAS_TOKEN", "")
    # Base publica (ex: https://clinica.com) pra montar links em e-mails/jobs
    # fora de um request (cron). Vazio = links sao omitidos.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

    # Chatbot de ajuda ("Nous Assistente") via Claude API. A chave fica SO no
    # servidor (nunca vai ao front). AJUDA_IA_ATIVA liga/desliga a feature sem
    # deploy; se a chave faltar, a feature fica inativa mesmo com a flag on.
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL_AJUDA = os.getenv("MODEL_AJUDA", "claude-haiku-4-5")
    AJUDA_IA_ATIVA = os.getenv("AJUDA_IA_ATIVA", "false").lower() in ("1", "true", "sim")

    # WhatsApp Business (Cloud API), multi-tenant. Feature INERTE por padrao:
    # WHATSAPP_ATIVO (global) liga o modulo; cada clinica conecta seu numero/token
    # (cifrado em repouso). So ha custo quando uma clinica conecta e envia — e o
    # billing da Meta e da clinica, nao nosso. Ver docs/10-whatsapp-integracao.md.
    WHATSAPP_ATIVO = os.getenv("WHATSAPP_ATIVO", "false").lower() in ("1", "true", "sim")
    WHATSAPP_API_BASE = os.getenv("WHATSAPP_API_BASE", "https://graph.facebook.com/v21.0")
    # Handshake do webhook (GET hub.verify_token) e assinatura (POST X-Hub-Signature-256).
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    # Chave Fernet pra cifrar o token de acesso em repouso. Vazio = deriva do
    # SECRET_KEY (rotacionar o SECRET_KEY invalida os tokens — recolar na clinica).
    WHATSAPP_ENC_KEY = os.getenv("WHATSAPP_ENC_KEY", "")

    # Emissao de NFS-e (nota fiscal de servico), multi-tenant via GATEWAY. Feature
    # INERTE por padrao: NF_ATIVO (global) liga o modulo; cada clinica configura seu
    # emitente (certificado A1 vai pro gateway). Ver docs/11-emissao-nf.md.
    NF_ATIVO = os.getenv("NF_ATIVO", "false").lower() in ("1", "true", "sim")
    # Gateway padrao + credenciais (OAuth2 client_credentials). Sandbox por padrao;
    # o segredo fica SO no servidor (variavel de ambiente), nunca no codigo/repo.
    NUVEMFISCAL_CLIENT_ID = os.getenv("NUVEMFISCAL_CLIENT_ID", "")
    NUVEMFISCAL_CLIENT_SECRET = os.getenv("NUVEMFISCAL_CLIENT_SECRET", "")
    NUVEMFISCAL_AMBIENTE = os.getenv("NUVEMFISCAL_AMBIENTE", "sandbox")  # sandbox|producao

    # TTL absoluto da sessao logada. Dados de saude sao sensiveis (LGPD) —
    # 8h forca re-login no dia seguinte. Ajuste conforme risco.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # Timeout por INATIVIDADE (idle): desloga apos N segundos sem requisicao.
    # Protege estacao compartilhada (recepcao) deixada aberta. 0/None desliga.
    IDLE_SESSION_LIFETIME = int(os.getenv("IDLE_SESSION_LIFETIME", "1800"))  # 30 min

    # Flask-Caching: SimpleCache in-memory por processo. Redis em multi-worker.
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 30

    # Flask-Limiter storage. memory:// em dev/test; redis em prod multi-worker.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    """Configuracao para a suite pytest. NUNCA toca o DB de dev."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL") or "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-never-use-in-prod"
    CACHE_TYPE = "NullCache"
    RATELIMIT_STORAGE_URI = "memory://"
    # Suite hermetica: ignora um .env de dev que tenha features ligadas. Cada
    # teste que precisa liga a flag/segredo explicitamente.
    AJUDA_IA_ATIVA = False
    ANTHROPIC_API_KEY = ""
    WHATSAPP_ATIVO = False
    WHATSAPP_VERIFY_TOKEN = "test-verify-token"
    WHATSAPP_APP_SECRET = ""          # vazio => sem checagem de assinatura no teste
    WHATSAPP_ENC_KEY = ""             # deriva do SECRET_KEY de teste


class ProductionConfig(Config):
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 3,
        "max_overflow": 5,
    }
    CACHE_TYPE = "RedisCache" if os.getenv("CACHE_REDIS_URL") else "SimpleCache"
    CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}