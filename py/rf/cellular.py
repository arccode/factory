# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functions across different cellular modules."""

import re

import factory_common  # pylint: disable=W0611

from cros.factory.utils.process_utils import Spawn

MODEM_STATUS = ['modem', 'status']
MODEM_IMEI_REG_EX = 'imei: ([0-9]*)'


def GetIMEI():
  '''Gets the IMEI of current active modem.'''
  stdout = Spawn(MODEM_STATUS, read_stdout=True,
                 log_stderr_on_error=True, check_call=True).stdout_data
  return re.search(MODEM_IMEI_REG_EX, stdout).group(1)
