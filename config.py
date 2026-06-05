import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base. SECRET_KEY tem fallback aleatorio aqui (overridable por subclasses)."""
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///nous.db"
    )
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

    # TTL da sessao logada. Dados de saude sao sensiveis (LGPD dados
    # sensiveis) — 8h forca re-login no dia seguinte. Ajuste conforme risco.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

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