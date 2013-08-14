# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import sys


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
  # See README on how to obtain this file.
  try:
    with file('privatekey.pem', 'r') as f:
      GOOGLE_API_PRIVATE_KEY = f.read()
  except IOError:
    logging.exception('private key for Google API Service Account not found.' +
                      ' (should be at privatekey.pem)')
    sys.exit(os.EX_DATAERR)

  # The google api id associated with the private key.
  from settings_bigquery import GOOGLE_API_ID  # pylint: disable=W0611
  # The project id and dataset id for data in bigquery.
  from settings_bigquery import PROJECT_ID  # pylint: disable=W0611
  from settings_bigquery import DATASET_ID  # pylint: disable=W0611

else:
  RELEASE_ROOT = '/var/db/factory'
  # Search the default path of Minijack DB.
  # TODO(waihong): Make it a command line option.
  for path in [os.path.join(PROJECT_ROOT, 'minijack_db'),
               os.path.join(PROJECT_ROOT, '..', 'minijack_db'),
               os.path.join(RELEASE_ROOT, 'minijack_db')]:
    if os.path.exists(path):
      MINIJACK_DB_PATH = path
      break
  else:
    logging.exception('Minijack database not found.')
    sys.exit(os.EX_DATAERR)
