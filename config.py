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