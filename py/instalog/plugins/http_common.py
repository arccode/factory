# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HTTP plugin common file."""

import logging

from cros.factory.instalog.external import gnupg


DEFAULT_PORT = 8899
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2gb
REQUESTED_GNUPG_VERSION = '0.4.3'
HTTP_TIMEOUT = 30  # Output HTTP Post timeout and Input HTTP socket timeout


def CheckGnuPG():
  if not gnupg.MODULE_READY:
    logging.error('Can not import package python-gnupg. '
                  'Did you run instalog/setup.py?')
    raise ImportError
  if gnupg.__version__ != REQUESTED_GNUPG_VERSION:
    logging.error('Please use package python-gnupg instead of gnupg. '
                  'Did you run instalog/setup.py?')
    raise ImportError
