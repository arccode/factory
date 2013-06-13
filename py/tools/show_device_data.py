#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tiny tools to dump the DeviceData.

Some components information are stored under DeviceData. This tiny tools
can pretty print the DeviceData.
"""

import pprint

import factory_common  # pylint: disable=W0611
from cros.factory.test import shopfloor

def main():
  pprint.pprint(shopfloor.GetDeviceData())

if __name__ == '__main__':
  main()
