"""Django settings for the RustDesk API and browser console."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from .env import env_bool, env_int, env_list, env_str, is_valid_secret_key, load_env_file

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# 运行时数据目录：源码运行时默认项目根；PyInstaller 打包版由启动脚本指向可执行文件旁。
DATA_DIR = Path(env_str("DATA_DIR", str(BASE_DIR)))
# 支持项目根目录与数据目录的 .env（已存在的环境变量优先，方便 systemd/容器覆盖）
load_env_file(BASE_DIR / ".env")
if DATA_DIR != BASE_DIR:
    load_env_file(DATA_DIR / ".env")

# SECURITY WARNING: don't run with debug turned on in production!
# 兼容旧写法：DEBUG=1/true/yes/on 才为真；DEBUG=False/0 不再被当成真值。
DEBUG = env_bool("DEBUG", False)

SECRET_KEY = env_str("SECRET_KEY")
if DEBUG and not SECRET_KEY:
    SECRET_KEY = get_random_secret_key()
elif not DEBUG and not is_valid_secret_key(SECRET_KEY):
    raise ImproperlyConfigured(
        "SECRET_KEY 必须是至少 50 位的随机字符串，且不能使用旧版默认值。"
        "生成方法：python -c \"import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))\""
        "，写入项目根目录的 .env 后重启服务。详见 docs/deployment.md 的「环境变量」一节。"
    )

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
# 远程部署填写实际访问域名或 IP。
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["127.0.0.1", "localhost", "[::1]"])
# 反向代理/HTTPS 场景下允许的来源，逗号分隔
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    [
        "http://127.0.0.1:21114",
        "http://localhost:21114",
        "http://127.0.0.1:5173",
        "http://localhost:5173",  # Vite 开发代理
    ],
)
SECURE_CROSS_ORIGIN_OPENER_POLICY = "None" if DEBUG else "same-origin"
AUTH_USER_MODEL = "api.UserProfile"  # AppName.自定义user

# 是否允许自助注册（1/true/yes/on 开启）
ALLOW_REGISTRATION = env_bool("ALLOW_REGISTRATION", False)
WEB_SETUP_TOKEN = env_str("WEB_SETUP_TOKEN")

# ========== 安全与运维 ==========
# 是否启用 Django 密码强度校验（生产环境建议开启）
PASSWORD_VALIDATION = env_bool("PASSWORD_VALIDATION", True)
# 登录失败节流：窗口内失败次数达到上限后锁定该 IP+账号
LOGIN_MAX_ATTEMPTS = env_int("LOGIN_MAX_ATTEMPTS", 8)
LOGIN_LOCK_SECONDS = env_int("LOGIN_LOCK_SECONDS", 300)
# 心跳写放大控制：设备在线时间戳最多每 N 秒写一次；token 只在剩余不足 M 秒时续期。
# 这两个值直接决定「每台设备每分钟的写库次数」，是支撑大规模设备的关键参数。
HEARTBEAT_DEVICE_TOUCH_SECONDS = env_int("HEARTBEAT_DEVICE_TOUCH_SECONDS", 120)
# 客户端 token 有效期（秒），默认 30 天。离线超过该时长才需要重新登录；
# 携带有效令牌的请求会在剩余不足 HEARTBEAT_TOKEN_REFRESH_SECONDS 时续期。
TOKEN_TTL_SECONDS = env_int("TOKEN_TTL_SECONDS", 30 * 24 * 3600)
HEARTBEAT_TOKEN_REFRESH_SECONDS = env_int("HEARTBEAT_TOKEN_REFRESH_SECONDS", 24 * 3600)
# 旧版 32 位令牌的过渡期：首次使用后最多再保留这么多秒，到期后必须重新登录。
# 注册/初始化的防滥用阈值（每个来源 IP，每小时）。
REGISTER_MAX_PER_HOUR = env_int("REGISTER_MAX_PER_HOUR", 10)
# --- OIDC 登录（可选） -------------------------------------------------------
# 同时配置 issuer/client_id/client_secret 才会启用；回调地址默认由客户端上报的
# API 域名 + /api/oidc/callback 推导，也可以在 IdP 侧固定后写入 OIDC_REDIRECT_URI。
OIDC_ISSUER = env_str("OIDC_ISSUER", "")
OIDC_CLIENT_ID = env_str("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = env_str("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = env_str("OIDC_REDIRECT_URI", "")
OIDC_SCOPES = env_str("OIDC_SCOPES", "openid profile email")
OIDC_BUTTON_LABEL = env_str("OIDC_BUTTON_LABEL", "OIDC")
OIDC_USERNAME_CLAIM = env_str("OIDC_USERNAME_CLAIM", "preferred_username")
OIDC_AUTO_CREATE = env_bool("OIDC_AUTO_CREATE", True)
OIDC_MAX_PER_HOUR = env_int("OIDC_MAX_PER_HOUR", 60)
OIDC_ALLOW_EMAIL_LINK = env_bool("OIDC_ALLOW_EMAIL_LINK", False)
SETUP_MAX_PER_HOUR = env_int("SETUP_MAX_PER_HOUR", 10)
# 「设备在线」判定窗口：必须大于 HEARTBEAT_DEVICE_TOUCH_SECONDS，
# 否则两次写库之间设备会被误判成离线（客户端心跳 15 秒一次，但时间戳不是每次都写）。
DEVICE_ONLINE_SECONDS = env_int("DEVICE_ONLINE_SECONDS", 300)

# 网页远控（/web/）的客户端配置：由 /api/webclient/config.js 动态下发（需已登录控制台会话），
# 与 API 服务共用同一份部署配置，并自动共享控制台登录态，无需在网页端二次登录。
ID_SERVER = env_str("ID_SERVER", "")
API_SERVER = env_str("API_SERVER", "")
RELAY_SERVER = env_str("RELAY_SERVER", "")
RUSTDESK_KEY = env_str("RUSTDESK_KEY", "")
# 免安装包/裸机运行时由 Django 直接提供网页远控静态文件；Docker 由内置 nginx + auth_request 接管。
WEBCLIENT_ROOT = env_str("WEBCLIENT_ROOT", str(BASE_DIR / "webroot" / "web"))
# 会话录像存放目录
RECORD_ROOT = env_str("RECORD_ROOT", os.path.join(str(DATA_DIR), "records"))

# 部署在 HTTPS/反向代理后：HTTPS=1 开启安全 Cookie、HSTS 与 SSL 跳转；
# BEHIND_PROXY=1 时信任外层代理传入的 X-Forwarded-Proto 与 X-Forwarded-For；
# INTERNAL_PROXY=1 由 Docker 镜像入口脚本自动设置，表示前方存在容器内置 nginx。
HTTPS = env_bool("HTTPS", False)
BEHIND_PROXY = env_bool("BEHIND_PROXY", False)
INTERNAL_PROXY = env_bool("INTERNAL_PROXY", False)
_trusted_proxy_raw = os.environ.get("TRUSTED_PROXY_COUNT", "").strip()
TRUSTED_PROXY_COUNT = max(0, int(_trusted_proxy_raw)) if _trusted_proxy_raw.isdigit() else None
if BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", HTTPS)
SECURE_REDIRECT_EXEMPT = [r"^api/health/?$"]
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", HTTPS)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", HTTPS)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000 if HTTPS else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
SECURE_HSTS_PRELOAD = HTTPS
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 1209600)


# ==========数据库配置 开始=====================
# 数据库类型：SQLITE（默认）/ MYSQL / POSTGRES
DATABASE_TYPE = env_str("DATABASE_TYPE", "SQLITE").upper()
# 通用 DB_* 变量优先；为兼容旧部署，没有 DB_* 时回落到原有 MYSQL_* 变量
DB_NAME = env_str("DB_NAME", os.environ.get("MYSQL_DBNAME", "-"))
DB_USER = env_str("DB_USER", os.environ.get("MYSQL_USER", "-"))
DB_PASSWORD = env_str("DB_PASSWORD", os.environ.get("MYSQL_PASSWORD", "-"))
DB_HOST = env_str("DB_HOST", os.environ.get("MYSQL_HOST", "127.0.0.1"))
_DEFAULT_DB_PORT = "5432" if DATABASE_TYPE.startswith("POSTGRES") else "3306"
DB_PORT = env_str("DB_PORT", os.environ.get("MYSQL_PORT", _DEFAULT_DB_PORT))
DB_CONN_MAX_AGE = env_int("DB_CONN_MAX_AGE", 60)
# 兼容旧变量名（views/管理脚本可能引用）
MYSQL_DBNAME, MYSQL_HOST = DB_NAME, DB_HOST
MYSQL_USER, MYSQL_PASSWORD, MYSQL_PORT = DB_USER, DB_PASSWORD, DB_PORT
# ==========数据库配置 结束=====================

LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "zh-hans")

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    # 客户端 API 在 api/urls.py 里单独 csrf_exempt；控制台/Admin 走 Session，必须校验 CSRF
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rustdesk_server_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rustdesk_server_api.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db/db.sqlite3",
        # 写锁等待时间；配合 api/db_pragmas.py 的 WAL 模式，单机也能扛住并发心跳
        "OPTIONS": {"timeout": env_int("SQLITE_TIMEOUT", 20)},
    }
}
_DB_READY = DB_NAME != "-" and DB_USER != "-"
if DATABASE_TYPE == "MYSQL" and _DB_READY:
    # 简单通过数据库名、账密信息过滤下，防止用户未配置mysql却使用mysql
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": DB_NAME,  # 数据库名
            "HOST": DB_HOST,  # 数据库服务器IP
            "USER": DB_USER,  # 数据库用户名
            "PASSWORD": DB_PASSWORD,  # 数据库密码
            "PORT": DB_PORT,  # 端口
            "CONN_MAX_AGE": DB_CONN_MAX_AGE,
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
elif DATABASE_TYPE in ("POSTGRES", "POSTGRESQL", "PG") and _DB_READY:
    # 生产推荐：Postgres 的并发写与连接池表现远好于 SQLite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": DB_NAME,
            "HOST": DB_HOST,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "PORT": DB_PORT,
            "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        }
    }

# ========== 缓存（登录节流 / 会话） ==========
# CACHE_URL 形如 redis://127.0.0.1:6379/0（或 rediss://、unix://）；
# 配了 Redis 且安装了 django-redis 时用 Redis，多进程/多实例下限流才会全局生效。
# 没配或没装依赖则退回进程内缓存（LocMem），功能可用但每个进程各算各的。
CACHE_URL = env_str("CACHE_URL", "")
if CACHE_URL.startswith(("redis://", "rediss://", "unix://")):
    try:
        import django_redis  # noqa: F401

        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": CACHE_URL,
                "KEY_PREFIX": "rustdesk",
                "TIMEOUT": 300,
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "IGNORE_EXCEPTIONS": True,
                    "SOCKET_CONNECT_TIMEOUT": 3,
                    "SOCKET_TIMEOUT": 3,
                },
            }
        }
        CACHE_BACKEND = "redis"
    except ImportError:
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rustdesk-locmem",
            }
        }
        CACHE_BACKEND = "locmem (未安装 django-redis)"
else:
    if env_str("CACHE_BACKEND", "").strip().lower() in ("db", "database"):
        # 数据库缓存：多 worker 共享计数，无需额外依赖；适合没有 Redis 的单机部署。
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "rustdesk_cache",
                "TIMEOUT": 300,
                "OPTIONS": {"MAX_ENTRIES": 5000},
            }
        }
        CACHE_BACKEND = "db"
    else:
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rustdesk-locmem",
            }
        }
        CACHE_BACKEND = "locmem"

# 健康检查详情（版本/DB/缓存）默认只对本机开放；远端监控可带此 token 读取。
HEALTH_TOKEN = env_str("HEALTH_TOKEN", "")

# ========== 日志 ==========
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOG_DIR = env_str("LOG_DIR", os.path.join(str(DATA_DIR), "logs"))
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError:  # 只读文件系统等场景下不阻断启动，仅保留控制台日志
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "app.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "api": {
            "handlers": ["console", "file"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_L10N = True

# USE_TZ = True
USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = "static/"

if DEBUG:
    STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

else:
    STATIC_ROOT = os.path.join(BASE_DIR, "static")  # 新增

LANGUAGES = (
    ("zh-hans", "中文简体"),
    ("en", "English"),
)
# Django 请求体上限。
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 10 * 1024 * 1024)
