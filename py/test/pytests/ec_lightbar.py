# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for Lightbar communication via EC.

The test uses "ectool" to check if the EC can talk to Lightbar.

It is ported from third_party/autotest/files/client/site_tests/hardware_EC.
"""

import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import process_utils


class ECLightbarTest(unittest.TestCase):
  """Tests EC communication with Lightbar."""

  def runTest(self):
    def _ECLightbar(cmd):
      try:
        return process_utils.CheckOutput(['ectool', 'lightbar'] + cmd.split(),
                                         log=True)
      except Exception as e:
        self.fail('Unable to set lightbar: %s' % e)

    _ECLightbar('on')
    _ECLightbar('init')
    _ECLightbar('4 255 255 255')
    response = _ECLightbar('')
    _ECLightbar('off')
    self.assertFalse(
        re.search(r'^ 05\s+3f\s+3f$', response, re.MULTILINE) is None,
        'Fail to match expected lightbar status: %s' % response)
