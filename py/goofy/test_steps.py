# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
Test steps run directly within Goofy.
'''

import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import updater
from cros.factory.test import factory
from cros.factory.test.factory import FactoryTest
from cros.factory.test.factory import TestState


class CheckUpdateStep(FactoryTest):
  '''Checks for updates and starts an update if available.

  Passes only once a definite response is available from the update server.
  '''
  def __init__(self, retries=10, retry_delay=2, **kw):
    super(CheckUpdateStep, self).__init__(invocation_target=self._Run,
                                          _default_id='CheckUpdateStep',
                                          **kw)
    self.retries = retries
    self.retry_delay = retry_delay

  def _Run(self, invocation):
    factory.console.info('Checking whether an update is available...')
    for count in range(1, self.retries + 1):
      try:
        md5sum, needs_update = updater.CheckForUpdate(
          invocation.goofy.test_list.options.shopfloor_timeout_secs)
        break
      except:  # pylint: disable=W0702
        # Unable to contact shopfloor server (e.g., machine just came
        # up and network is not yet available).  Wait and retry.
        if count == self.retries:
          # That's all folks.
          raise

        factory.console.info('Unable to contact shopfloor server. '
                             'Retrying... (%d/%d)', count, self.retries)
        time.sleep(self.retry_delay)
    if needs_update:
      factory.console.info('Updating to %s', md5sum)
      # Start the update process.
      invocation.goofy.run_queue.put(
        lambda: invocation.goofy.update_factory(auto_run_on_restart=True))
      raise factory.FactoryTestFailure('Pending update',
                                       status=TestState.UNTESTED)
    else:
      factory.console.info('Factory software is up to date')
