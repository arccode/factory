# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time


def Main(factory_automation, test_path):  # pylint: disable=W0613
  factory_automation.ectool_command.TurnOffAllUSBPower()
  factory_automation.ectool_command.TurnOnAllUSBPower()
  time.sleep(2)
  factory_automation.ectool_command.TurnOffAllUSBPower()
  factory_automation.ectool_command.TurnOnAllUSBPower()
