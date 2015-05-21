#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that cros.factory.* can be located."""

import os
import sys

# factory_common.py itself is usually a symlink that refers to top level of
# factory code. To find that, we need to get the source name (the compiled
# binary *.pyc is usually not a symlink), derive the path to "py_pkg" folder,
# and then append into Python path (sys.path) if it's not available yet.
# For platforms without symlink (i.e., Windows), we need to derive the top level
# by environment variable.

pk_pkg = os.path.join(
    os.getenv('CROS_FACTORY_ROOT',
              os.path.dirname(os.path.dirname(
                  os.path.realpath(__file__.replace('.pyc', '.py'))))),
    'py_pkg')

if pk_pkg not in sys.path:
  sys.path.append(pk_pkg)
