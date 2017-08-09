# Copyright 2012 The Chromium OS Authors. All rights reserved.
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

py_pkg = os.getenv(
    'CROS_FACTORY_PY_ROOT',
    os.path.join(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__.replace('.pyc', '.py')))), 'py_pkg'))

if py_pkg not in sys.path:
  sys.path.insert(0, py_pkg)
