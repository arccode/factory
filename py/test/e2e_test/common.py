# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common constants and utility methods."""


import factory_common  # pylint: disable=W0611
from cros.factory.test import utils


DEFAULT = '__DEFAULT__'
CHROOT = '__CHROOT__'

AutomationMode = utils.Enum(['NONE', 'PARTIAL', 'FULL'])
AutomationModePrompt = {
    AutomationMode.NONE: None,
    AutomationMode.PARTIAL: 'Partial automation mode; manual tests are run.',
    AutomationMode.FULL: 'Full automation mode; manual tests are skipped.'
}


def ParseAutomationMode(mode):
  """Parses the given mode string to AutomationMode enumeration.

  Args:
    mode: An automation mode string.

  Returns:
    The parsed Enum string.

  Raises:
    ValueError if the given mode string is invalid.
  """
  if mode.upper() not in AutomationMode:
    raise ValueError('Invalid mode string %r; valid values are: %r' %
                     (mode, list(AutomationMode)))
  return mode.upper()
