#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A test for make_par.py.

This also tests run_pytest.
'''


import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import make_par
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


class MakePARTest(unittest.TestCase):
  def testPAR(self):
    with file_utils.UnopenedTemporaryFile(suffix='.par') as par:
      self.assertTrue(make_par.main(['cros.factory.test.run_pytest',
                                     '-o', par]))

      for expected_retcode, script in ((0, 'pass'),
                                       (1, 'raise ValueError')):
        self.assertEquals(
            expected_retcode,
            Spawn([par, 'execpython', '--args', 'dict(script=%r)' % script],
                  log=True, call=True,
                  ignore_stdout=True, ignore_stderr=True).returncode)

  def testInvalidModule(self):
    with file_utils.UnopenedTemporaryFile(suffix='.par') as par:
      self.assertFalse(make_par.main(['cros.factory.nonexistant_module',
                                      '-o', par]))


if __name__ == '__main__':
  unittest.main()
