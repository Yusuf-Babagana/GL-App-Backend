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

# 3. Security & Debug (Read from .env ONLY)
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

ALLOWED_HOSTS = ['glappbackend.pythonanywhere.com', '127.0.0.1', 'localhost']

# 4. Auth & User Model
AUTH_USER_MODEL = 'users.User'

# 5. VTpass & Monnify (Read from .env)
VTPASS_API_KEY = env('VTPASS_API_KEY')
VTPASS_SECRET_KEY = env('VTPASS_SECRET_KEY')
VTPASS_BASE_URL = env('VTPASS_BASE_URL')

# Monnify (You can move these to .env later for better security)
MONNIFY_API_KEY = "MK_TEST_EHY73CFGYU"
MONNIFY_SECRET_KEY = "RP5NGLN5BC0ZZRQ98V3QUQ8D22MGSE5S"
MONNIFY_CONTRACT_CODE = "1022108728"
MONNIFY_BASE_URL = "https://sandbox.monnify.com/api/v1"




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
    'corsheaders.middleware.CorsMiddleware', # Add this at the top
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}


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


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True # For development only







SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1), # <--- Increase to 1 day for development
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer', 'Token'), # Allow both Bearer and Token prefixes
}



# Increase Upload Size for Video
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800 # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800 # 50 MB


# MONNIFY CONFIGURATION (TEST KEYS)
MONNIFY_API_KEY = "MK_TEST_EHY73CFGYU"
MONNIFY_SECRET_KEY = "RP5NGLN5BC0ZZRQ98V3QUQ8D22MGSE5S"
MONNIFY_CONTRACT_CODE = "1022108728"
MONNIFY_BASE_URL = "https://sandbox.monnify.com/api/v1"



# globalink_core/settings.py
VTPASS_API_KEY = "b913b36773efa776fa66ac89754ce5d9"
VTPASS_PUBLIC_KEY = "PK_6534ea14ddaa482fdd87d0e9fd033ef880bf2742543"
VTPASS_SECRET_KEY = "SK_396406b7ba5006e8b770cfbb5ec2fe25a97b3f389a2"
VTPASS_BASE_URL = "https://sandbox.vtpass.com/api" # Use sandbox for testing today


# settings.py

STATIC_URL = '/static/'

# Add this line - it tells Django where to put static files for production
STATIC_ROOT = os.path.join(BASE_DIR, 'static') 

# If you have a separate folder for your custom assets, keep this:
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'staticfiles'), # Make sure this folder exists or remove this list
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')