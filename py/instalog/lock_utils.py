# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""multiprocessing-related utilities."""

from multiprocessing import synchronize

class Lock(synchronize.Lock):

  def locked(self):
    return self._semlock._is_mine()  # pylint: disable=protected-access
