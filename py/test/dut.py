#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides backward compatibility for Device-Aware API.

Previously the Device-Aware API is serving DUT only, located in
cros.factory.test.dut. The new location is cros.factory.device
so here we have to create a 'dut' module that forwards all APIs
for old tests to run.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory import device
from cros.factory.device import board  # pylint: disable=unused-import
from cros.factory.device import component
from cros.factory.device import device_utils

# locals().update is a special trick to fully simulate importing sub packages.
# If we do 'from cros.factory.device import *', then people using legacy code
# like 'from cros.factory.test.dut.board import DUTBoard' would fail.
locals().update(device.__dict__)

# Legacy names
Create = device_utils.CreateDUTInterface
CreateLocal = device_utils.CreateStationInterface
DUTException = component.DeviceException
DUTComponent = component.DeviceComponent
DUTProperty = component.DeviceProperty
