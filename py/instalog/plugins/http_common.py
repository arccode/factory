# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HTTP plugin common file."""

import logging

import instalog_common  # pylint:disable=unused-import
from instalog.external import gnupg


DEFAULT_PORT = 8899
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2gb
REQUESTED_GNUPG_VERSION = '2.3.0'


def CheckGnuPG():
  if not gnupg.MODULE_READY:
    logging.error('Can not import gnupg package. '
                  'Did you run instalog/setup.py?')
    raise ImportError
  if gnupg.__version__ != REQUESTED_GNUPG_VERSION:
    logging.error('Please use package gnupg instead of python-gnupg. '
                  'Did you run instalog/setup.py?')
    raise ImportError
