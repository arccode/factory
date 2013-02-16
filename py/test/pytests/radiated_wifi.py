# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.pytests.rf_framework import RfFramework


class RadiatedWifi(RfFramework, unittest.TestCase):
  def PreTestOutsideShieldBox(self):
    factory.console.info('PreTestOutsideShieldBox called')
    # TODO(itspeter): Switch to factory specific drivers.

  def PreTestInsideShieldBox(self):
    factory.console.info('PreTestInsideShieldBox called')
    # TODO(itspeter): Ask user to enter shield box information.
    # TODO(itspeter): Check the existence of Ethernet.
    # TODO(itspeter): Verify the validity of shield-box and calibration_config.

  def PrimaryTest(self):
    # TODO(itspeter): Implement the primary test snippet.
    pass

  def PostTest(self):
    # TODO(itspeter): Switch to production drivers.
    # TODO(itspeter): Upload result to shopfloor server.
    # TODO(itspeter): Determine the test result and save to csv file.
    pass

  def DownloadParameters(self):
    # TODO(itspeter): Sync time with shopfloor.
    # TODO(itspeter): Download parameters based on list args.parameters.
    # TODO(itspeter): Verify the signature of parameters.
    pass
