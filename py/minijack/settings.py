# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os


SECRET_KEY = 'qn5@1t%&%nnq5mtbkm*w&#u@uj4w8unl^2c6iq8e2ke9r=v)ap'

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Django settings:

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ROOT_URLCONF = 'urls'

INSTALLED_APPS = (
    'django.contrib.staticfiles',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'frontend',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.core.context_processors.request',
)

TEMPLATE_DIRS = (
    os.path.join(os.path.dirname(__file__), 'templates'),
)

STATIC_URL = '/static/'

IS_APPENGINE = ('APPENGINE_RUNTIME' in os.environ)

if IS_APPENGINE:
  # Backend database want to use, 'bigquery' or 'cloud_sql'
  # This would change the import in db/__init__.py
  BACKEND_DATABASE = 'bigquery'
else:
  RELEASE_ROOT = '/var/db/factory'
  # Search the default path of Minijack DB.
  # TODO(waihong): Make it a command line option.
  MINIJACK_DB_PATH = None
  for path in [os.path.join(PROJECT_ROOT, 'frontend', 'minijack_db'),
               os.path.join(PROJECT_ROOT, 'minijack_db'),
               os.path.join(RELEASE_ROOT, 'minijack_db')]:
    if os.path.exists(path):
      MINIJACK_DB_PATH = path
      break
