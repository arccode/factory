# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types


# Forward the exception for easy access to all device (component, interface,
# board) exceptions.
DeviceException = types.DeviceException
DeviceProperty = types.DeviceProperty
DeviceComponent = types.DeviceComponent
DeviceInterface = types.DeviceInterface
CalledProcessError = types.CalledProcessError
