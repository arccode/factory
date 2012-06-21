#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common
from autotest_lib.client.cros.factory.system import SystemStatus


class SystemStatusTest(unittest.TestCase):
    def runTest(self):
        # Don't care about the values; just make sure there's something
        # there.
        status = SystemStatus()
        # Don't check battery, since this system might not even have one.
        self.assertTrue(isinstance(status.battery, dict))
        self.assertEquals(3, len(status.loadavg))
        self.assertEquals(10, len(status.cpu))


if __name__ == "__main__":
    unittest.main()
