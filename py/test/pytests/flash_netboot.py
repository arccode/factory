# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Flash system main (AP) firmware to netboot firmware.

Description
-----------
Sometimes in order to re-run factory flow, or to update partitions that can't be
updated by Chrome OS Factory Software (for example, the disk partition itself,
or release and test image rootfs), we may want to flash system firmware and
restart the process.

The `flash_netboot` test provides an easy way to flash netboot firmware into
system using `flashrom` utility, and preserving VPD sections.

Note that it doesn't reboot after flashing firmware. Please run reboot
step after it.

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will reflash system firmware using specified image.

Dependency
----------
- Utility `flashrom` (https://www.flashrom.org/Flashrom).
- System firmware is structured with FMAP.
- Chrome OS Verified Boot firmware utility 'futility'.

Examples
--------
To flash netboot firmware in provided default location, add this in test list::

  {
    "pytest_name": "flash_netboot"
  }

To flash netboot firmware from a special location::

  {
    "pytest_name": "flash_netboot",
    "args": {
      "image": "/usr/local/factory/3rdparty/netboot.bin"
    }
  }
"""

import logging

from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.tools import flash_netboot
from cros.factory.utils.arg_utils import Arg


class FlashNetbootTest(test_case.TestCase):
  ARGS = [
      Arg('image', str,
          ('Path of netboot firmware image. Default to use %s' %
           flash_netboot.DEFAULT_NETBOOT_FIRMWARE_PATH),
          default=None),
  ]

  ui_class = test_ui.ScrollableLogUI

  def ShowResult(self, message):
    logging.info(message.strip())
    self.ui.AppendLog(message)

  def runTest(self):
    netboot_flasher = flash_netboot.FlashNetboot(self.args.image,
                                                 on_output=self.ShowResult)
    self.ShowResult(netboot_flasher.WarningMessage())
    netboot_flasher.Run()
