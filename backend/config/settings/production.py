from .base import *
from decouple import config
import dj_database_url
import os

DEBUG = False
SECRET_KEY = config('SECRET_KEY')

# Render injects RENDER_EXTERNAL_HOSTNAME automatically for every web service —
# e.g. "flatmates-backend.onrender.com". We trust that host plus anything
# explicitly listed in ALLOWED_HOSTS.
ALLOWED_HOSTS = []
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
ALLOWED_HOSTS += config('ALLOWED_HOSTS', default='').split(',')

DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        # conn_max_age=0 because we use Supabase's Supavisor connection
        # pooler (transaction mode, port 6543). Django's persistent
        # connection reuse (conn_max_age > 0) does not play well with
        # PgBouncer-style transaction pooling — each "connection" Django
        # holds open can end up multiplexed across different backend
        # sessions, which breaks session-level state. Set DB_CONN_MAX_AGE
        # to a positive number ONLY if you switch to Supabase's direct
        # connection (port 5432) instead of the pooler.
        conn_max_age=config('DB_CONN_MAX_AGE', default=0, cast=int),
        ssl_require=True,
    )
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Secure SSL settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Vercel frontend origin(s) — set as env vars on Render after Vercel deploy
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='').split(',')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='').split(',')
# CSRF_TRUSTED_ORIGINS must include the scheme, e.g.:
#   https://flatmates-frontend.vercel.app
# Also add the Render backend's own URL so Django admin login works over HTTPS:
#   https://flatmates-backend.onrender.com
