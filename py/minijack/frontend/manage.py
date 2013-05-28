#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys
from django.core.management import execute_from_command_line

import factory_common  # pylint: disable=W0611


if __name__ == '__main__':
  os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                        'cros.factory.minijack.frontend.settings')
  execute_from_command_line(sys.argv)
