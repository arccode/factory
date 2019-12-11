# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""multiprocessing-related utilities."""

import logging
from multiprocessing import synchronize


class Lock(synchronize.Lock):

  def __init__(self, logger_name):
    # Lock initialize with a default context if ctx is None.
    super(Lock, self).__init__(ctx=None)
    self.logger = logging.getLogger(logger_name)

  def IsHolder(self):
    """Checks the process and the thread is the holder of the lock."""
    return self._semlock._is_mine()  # pylint: disable=protected-access

  def CheckAndRelease(self):
    """Checks the holder and releases the lock."""
    if self.IsHolder():
      try:
        self.release()
      except Exception:
        self.logger.exception('Exception encountered in CheckAndRelease')
