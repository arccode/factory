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

import logging
import time
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
        default=(), optional=True),
    Arg('retry_secs', (int, float),
        'retry interval in seconds (or None for no retry)',
        optional=True),
    ]

  def runTest(self):
    while True:
      fixture = None
      try:
        fixture = CreateBFTFixture(**self.args.bft_fixture)
        getattr(fixture, self.args.method)(*self.args.args)
        break  # Success; we're done
      except:  # pylint: disable=W0702
        logging.exception('BFT fixture test failed')
        if not self.args.retry_secs:
          # No retry; raise the exception to fail the test
          raise
      finally:
        if fixture:
          try:
            fixture.Disconnect()
          except:  # pylint: disable=W0702
            logging.exception('Unable to disconnect fixture')

      logging.info('Will retry in %s secs', self.args.retry_secs)
      time.sleep(self.args.retry_secs)
