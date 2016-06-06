# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that instalog.* can be located."""

import os
import sys

# instalog_common.py itself is usually a symlink that refers to the parent level
# of instalog code. To find that, we need to get the source name (the compiled
# binary *.pyc is usually not a symlink), derive the path to the parent folder,
# and then append into Python path (sys.path) if it's not available yet.
# For platforms without symlink (i.e., Windows), we need to derive the top level
# by environment variable.

py_dir = os.getenv(
    'INSTALOG_PY_ROOT',
    os.path.join(os.path.dirname(
        os.path.realpath(__file__.replace('.pyc', '.py'))), '..'))

if py_dir not in sys.path:
  sys.path.append(py_dir)
