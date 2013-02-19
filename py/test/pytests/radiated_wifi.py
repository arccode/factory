# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import utils
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
    """Downloads parameters from shopfloor and saved to state/caches."""
    factory.console.info('Start downloading parameters...')
    _SHOPFLOOR_TIMEOUT_SECS = 10 # Timeout for shopfloor connection.
    _SHOPFLOOR_RETRY_INTERVAL_SECS = 10 # Seconds to wait between retries.
    while True:
      try:
        logging.info('Syncing time with shopfloor...')
        goofy = factory.get_state_instance()
        goofy.SyncTimeWithShopfloorServer()

        # Listing files on args.parameters
        download_list = []
        shopfloor_client = shopfloor.get_instance(
            detect=True, timeout=_SHOPFLOOR_TIMEOUT_SECS)
        for glob_expression in self.args.parameters:
          logging.info('Listing %s', glob_expression)
          download_list.extend(
              shopfloor_client.ListParameters(glob_expression))
        logging.info('Download list prepared:\n%s', '\n'.join(download_list))
        # Download the list and saved to caches in state directory.
        caches_dir = os.path.join(CACHES_DIR, 'parameters')
        for filepath in download_list:
          utils.TryMakeDirs(os.path.join(
              caches_dir, os.path.dirname(filepath)))
          binary_obj = shopfloor_client.GetParameter(filepath)
          open(os.path.join(caches_dir, filepath), 'wb').write(binary_obj.data)
        return
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        # Log only the exception string, not the entire exception,
        # since this may happen repeatedly.
        factory.console.info('Unable to sync with shopfloor server: %s',
                             exception_string)
      time.sleep(_SHOPFLOOR_RETRY_INTERVAL_SECS)

    # TODO(itspeter): Verify the signature of parameters.
