# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'scan' test."""

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class ScanAutomator(Automator):
  """The 'scan' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'scan'

  @AutomationFunction(automation_mode=(AutomationMode.PARTIAL,
                                       AutomationMode.FULL))
  def automateScanDefault(self):
    # For scanning MLB serial number.
    if self.args.label_en == 'MLB Serial Number':
      self.uictl.SetElementValue('scan-value', 'TESTMLB-%s' %
                                 net_utils.GetWLANMACAddress())

    # For scanning device serial number.
    elif self.args.label_en == 'Device Serial Number':
      self.uictl.SetElementValue('scan-value', 'TESTDEV-%s' %
                                 net_utils.GetWLANMACAddress())

    # For scanning operator ID.
    elif self.args.label_en == 'Operator ID':
      self.uictl.SetElementValue('scan-value', 'Automator')

    self.uictl.PressKey(self.uictl.KEY_ENTER)
