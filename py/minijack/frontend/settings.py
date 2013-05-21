# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import sys


# Search the default path of Minijack DB.
# TODO(waihong): Make it a command line option.
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
for path in [os.path.join(PROJECT_ROOT, 'minijack_db'),
             os.path.join(PROJECT_ROOT, '..', 'minijack_db'),
             '/var/db/factory/minijack_db']:
  if os.path.exists(path):
    minijack_db_path = path
    break
else:
  logging.exception('Minijack database not found.')
  sys.exit(os.EX_DATAERR)


# Django settings:

DEBUG = True
TEMPLATE_DEBUG = DEBUG

DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': minijack_db_path,
  }
}

WSGI_APPLICATION = 'frontend.wsgi.application'
ROOT_URLCONF = 'frontend.urls'

STATIC_ROOT = os.path.join(PROJECT_ROOT, 'static')
STATIC_URL = '/static/'
TEMPLATE_DIRS = os.path.join(PROJECT_ROOT, 'templates')
