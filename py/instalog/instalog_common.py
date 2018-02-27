# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that instalog.* can be located."""

import os
import sys

# instalog_common.py itself is usually a symlink that recursively resolves to a
# file in the root level of Instalog code.  To set up the proper Python path
# (sys.path), we need to get the source name (the compiled binary *.pyc is
# usually not a symlink) and derive the path to the root folder.  Then, we
# insert the parent directory into Python path if they are not yet available.
# For platforms without symlink (i.e., Windows), we need to derive the
# top level by environment variable.

INSTALOG_DIR = os.path.dirname(
    os.path.realpath(__file__.replace('.pyc', '.py')))
INSTALOG_PARENT_DIR = os.path.realpath(os.path.join(INSTALOG_DIR, '..'))
INSTALOG_VIRTUAL_ENV_DIR = (
    os.environ.get('VIRTUAL_ENV') or
    os.path.realpath(os.path.join(INSTALOG_DIR, 'virtual_env')))

if INSTALOG_PARENT_DIR not in sys.path:
  sys.path.insert(0, INSTALOG_PARENT_DIR)
