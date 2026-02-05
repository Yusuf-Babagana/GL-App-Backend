import os
import environ
from pathlib import Path
from datetime import timedelta

# 1. Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Initialize environment variables
env = environ.Env(DEBUG=(bool, False))
# Look for .env file specifically in the project root
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# 3. Security & Debug (Read from .env)
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

ALLOWED_HOSTS = ['glappbackend.pythonanywhere.com', '127.0.0.1', 'localhost']

# 4. Auth & User Model
AUTH_USER_MODEL = 'users.User'

# 5. Third Party Service Keys (Read from .env)
VTPASS_API_KEY = env('VTPASS_API_KEY')
VTPASS_SECRET_KEY = env('VTPASS_SECRET_KEY')
VTPASS_BASE_URL = env('VTPASS_BASE_URL')

# MONNIFY CONFIGURATION (TEST KEYS)
MONNIFY_API_KEY = "MK_TEST_EHY73CFGYU"
MONNIFY_SECRET_KEY = "RP5NGLN5BC0ZZRQ98V3QUQ8D22MGSE5S"
MONNIFY_CONTRACT_CODE = "1022108728"
MONNIFY_BASE_URL = "https://sandbox.monnify.com/api/v1"

# 6. Application Definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party
    'rest_framework',
    'rest_framework.authtoken',
    'dj_rest_auth',
    'corsheaders',

    # Local Apps
    'users',
    'market',
    'jobs',
    'logistics',
    'finance',
    'chat'
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'globalink_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'globalink_core.wsgi.application'

# 7. Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# 8. Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 9. Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# 10. Static & Media Files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Only include STATICFILES_DIRS if the folder actually exists locally
if os.path.exists(os.path.join(BASE_DIR, 'staticfiles')):
    STATICFILES_DIRS = [os.path.join(BASE_DIR, 'staticfiles')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# 11. API & Security Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer', 'Token'),
}

CORS_ALLOW_ALL_ORIGINS = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Upload Limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800