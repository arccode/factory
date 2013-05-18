# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An interface to command BFT fixture.

dargs:
  bft_fixture: {class_name: BFTFixture's import path + module name
                params: a dict of params for BFTFixture's Init()}.
  method: BFTFixture method to call.
  args: args of the method.
"""

import unittest

from cros.factory.test.args import Arg
from cros.factory.test.fixture.bft_fixture import CreateBFTFixture


class BFTFixture(unittest.TestCase):
  ARGS = [
    Arg('bft_fixture', dict,
        '{class_name: BFTFixture\'s import path + module name\n'
        ' params: a dict of params for BFTFixture\'s Init()}.\n'
        'Default None means no BFT fixture is used.'),
    Arg('method', str, 'BFTFixture method to call.'),
    Arg('args', (list, tuple), 'args of the method.',
        default=None, optional=True)]

  def setUp(self):
    self._fixture = None
    self._fixture = CreateBFTFixture(**self.args.bft_fixture)
    self._method = self.args.method
    self._method_args = self.args.args if self.args.args else ()

  def tearDown(self):
    if self._fixture:
      self._fixture.Disconnect()

  def runTest(self):
    getattr(self._fixture, self._method)(*self._method_args)
