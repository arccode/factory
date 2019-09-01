#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import codecs
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.doc import generate_rsts
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.file_utils import UnopenedTemporaryFile
from cros.factory.utils.type_utils import Enum


class GenerateDocsTest(unittest.TestCase):

  def testGenerateTestDocs(self):
    # A class that looks like a test module.
    class PseudoModule(object):  # pylint: disable=no-init
      """Module-level help."""
      class FooTest(unittest.TestCase):
        ARGS = [
            Arg('a', int, 'A', default=1),
            Arg('b', Enum(['b1', 'b2']),
                'Foo:\n'
                '\n'
                '  - bar\n'
                '  - baz\n',
                default='b1'),
        ]
        def runTest(self):
          pass

    with UnopenedTemporaryFile() as temp:
      with codecs.open(temp, 'w', 'utf-8') as out:
        with mock.patch(
            'cros.factory.test.utils.pytest_utils.LoadPytestModule') as lpm:
          lpm.return_value = PseudoModule

          generate_rsts.GenerateTestDocs(
              generate_rsts.RSTWriter(out), 'pseudo_test')

      with open(temp) as f:
        lines = f.read().splitlines()

      self.maxDiff = None
      self.assertEquals(
          ['pseudo_test',
           '===========',
           'Module-level help.',
           '',
           'Test Arguments',
           '--------------',
           '.. list-table::',
           '   :widths: 20 10 60',
           '   :header-rows: 1',
           '',
           '   * - Name',
           '     - Type',
           '     - Description',
           '',
           '   * - a',
           '     - int',
           '     - (optional; default: ``1``) A',
           '',
           '   * - b',
           "     - ['b1', 'b2']",
           '     - (optional; default: ``\'b1\'``) Foo:',
           '       ',
           '         - bar',
           '         - baz',
           ''],
          lines)


if __name__ == '__main__':
  unittest.main()
