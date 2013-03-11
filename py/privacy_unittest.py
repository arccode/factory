#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest2

import factory_common  # pylint: disable=W0611
from cros.factory import privacy

class PrivacyTest(unittest2.TestCase):
  def testFilterDict(self):
    self.assertEquals(
        dict(a='A', b='B',
             ubind_attribute='<redacted 1 chars>',
             gbind_attribute='<redacted 2 chars>'),
        privacy.FilterDict(
            dict(a='A', b='B', ubind_attribute='U', gbind_attribute='GG')))

if __name__ == '__main__':
  unittest2.main()
