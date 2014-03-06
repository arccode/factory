#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import codecs
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.doc import generate_rsts
from cros.factory.test.args import Arg
from cros.factory.test.utils import Enum
from cros.factory.utils.file_utils import UnopenedTemporaryFile


class GenerateDocsTest(unittest.TestCase):
  def testGenerateTestDocs(self):
    # A class that looks like a test module.
    class PseudoModule:  # pylint: disable=W0232
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

    with UnopenedTemporaryFile() as temp:
      with codecs.open(temp, 'w', 'utf-8') as out:
        generate_rsts.GenerateTestDocs('pseudo_test', PseudoModule, out)
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
         '   * - a',
         '     - int',
         '     - (optional; default: ``1``) A',
         '   * - b',
         '     - [b1, b2]',
         '     - (optional; default: ``\'b1\'``) Foo:',
         '       ',
         '         - bar',
         '         - baz',
          ],
        lines)


if __name__ == '__main__':
  unittest.main()
