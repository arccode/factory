#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.test.pytests import keyboard
from cros.factory.utils import schema


class KeyboardUnitTest(unittest.TestCase):

  def testValidDataWithKeymapSchema(self):
    valid_data = [{
        "0": "1"
    }, {
        "0b1": "0b1"
    }, {
        "0o1": "0o1"
    }, {
        "0x1": "0x1"
    }]
    for data in valid_data:
      try:
        # pylint: disable=protected-access
        self.assertEqual(None,
                         keyboard._REPLACEMENT_KEYMAP_SCHEMA.Validate(data))
      except Exception as err:
        raise Exception('data is not valid: %r' % data) from err

  def testInvalidDataWithKeymapSchema(self):
    invalid_data = [{
        "x": "1"
    }, {
        "01": "1"
    }, {
        1: "1"
    }, {
        "1": "x"
    }, {
        "1": "01"
    }, {
        "1": 1
    }]
    for data in invalid_data:
      try:
        # pylint: disable=protected-access
        self.assertRaisesRegex(schema.SchemaException, '^.*$',
                               keyboard._REPLACEMENT_KEYMAP_SCHEMA.Validate,
                               data)
      except Exception as err:
        raise Exception('data is not invalid: %r' % data) from err


if __name__ == '__main__':
  unittest.main()
