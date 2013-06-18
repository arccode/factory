#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils.string_utils import ParseDict


_LINES = ['TPM Enabled: true',
          'TPM Owned: false',
          'TPM Being Owned: false',
          'TPM Ready: false',
          'TPM Password:']
_DICT_RESULT = {'TPM Being Owned': 'false',
                'TPM Ready': 'false',
                'TPM Password': '',
                'TPM Enabled': 'true',
                'TPM Owned': 'false'}


class ParseDictTest(unittest.TestCase):
  def testParseDict(self):
    self.assertEquals(_DICT_RESULT, ParseDict(_LINES, ':'))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
