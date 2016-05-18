#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.device import component


# Forward the exception for easy access to all DUT (board, component)
# exceptions.
DeviceException = component.DeviceException
DeviceComponent = component.DeviceComponent
CalledProcessError = component.CalledProcessError
