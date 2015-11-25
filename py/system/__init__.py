# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Interfaces to set and get system status and system information."""

from __future__ import print_function

import glob
import os
import threading

import factory_common  # pylint: disable=W0611
from cros.factory import test
from cros.factory.test.utils import ReadOneLine

# pylint: disable=W0702
# Disable checking of exception types, since we catch all exceptions
# in many places.

_board = None
_lock = threading.Lock()


def GetBoard():
  """Returns a board instance for the device under test.

  By default, a
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` object
  is returned, but this may be overridden by setting the
  ``CROS_FACTORY_BOARD_CLASS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Returns:
    An instance of the specified Board class implementation.
  """
  # pylint: disable=W0603
  with _lock:
    global _board
    if _board:
      return _board

    board = os.environ.get('CROS_FACTORY_BOARD_CLASS',
                           'cros.factory.board.chromeos_board.ChromeOSBoard')
    module, cls = board.rsplit('.', 1)
    _board = getattr(__import__(module, fromlist=[cls]), cls)()
    return _board


# TODO(hungte) Move this to a new display module when we have finished the new
# system module migration.
def SetBacklightBrightness(level):
  """Sets the backlight brightness level.

  Args:
    level: A floating-point value in [0.0, 1.0] indicating the backlight
        brightness level.

  Raises:
    ValueError if the specified value is invalid.
  """
  if not (level >= 0.0 and level <= 1.0):
    raise ValueError('Invalid brightness level.')
  interfaces = glob.glob('/sys/class/backlight/*')
  for i in interfaces:
    with open(os.path.join(i, 'brightness'), 'w') as f:
      f.write('%d' % int(
          level * float(ReadOneLine(os.path.join(i, 'max_brightness')))))
