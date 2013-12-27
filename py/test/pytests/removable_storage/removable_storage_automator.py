# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'removable_storage' test."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class RemovableStorageAutomator(Automator):
  """The 'removable_storage' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'removable_storage'

  @AutomationFunction(
      override_dargs=dict(
          sysfs_path='/sys/devices/12110000.usb/usb3/3-1/3-1:1.0'),
      automation_mode=AutomationMode.FULL, wait_for_factory_test=False)
  def automateSkipRemovableStorage(self):
    # Simply pass the test.
    self.uictl.WaitForContent(search_text='Removable Storage Test')
