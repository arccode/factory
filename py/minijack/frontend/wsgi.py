# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
from django.core.wsgi import get_wsgi_application

import factory_common  # pylint: disable=W0611


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'frontend.settings')
# The application object used by WSGI server.
application = get_wsgi_application()
