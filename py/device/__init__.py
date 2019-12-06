# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device import device_types


# Forward the exception for easy access to all device (component, interface,
# board) exceptions.
DeviceException = device_types.DeviceException
DeviceProperty = device_types.DeviceProperty
DeviceComponent = device_types.DeviceComponent
DeviceInterface = device_types.DeviceInterface
CalledProcessError = device_types.CalledProcessError
