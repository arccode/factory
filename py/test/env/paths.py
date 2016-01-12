#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=W0611


SCRIPT_PATH = os.path.realpath(__file__)
# Path to factory envrionment (code and resources)
FACTORY_PATH = os.path.realpath(os.path.join(SCRIPT_PATH, '..', '..', '..', '..'))
FACTORY_PACKAGE_PATH = os.path.join(FACTORY_PATH, 'py_pkg', 'cros', 'factory')
FACTORY_MD5SUM_PATH = os.path.join(FACTORY_PATH, 'MD5SUM')
FIRMWARE_UPDATER_PATH = os.path.join(
    FACTORY_PATH, 'board', 'chromeos-firmwareupdate')

# Path to stateful partition on device.
DEVICE_STATEFUL_PATH = '/mnt/stateful_partition'

# Name of Chrome data directory within the state directory.
CHROME_DATA_DIR_NAME = 'chrome-data-dir'
