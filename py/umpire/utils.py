# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire utility classes."""

from twisted.internet import defer

import factory_common  # pylint: disable=W0611
from cros.factory.common import AttrDict, Singleton


class Registry(AttrDict):
  """Registry is a singleton class that inherits from AttrDict.

  Example:
    config_file = Registry().get('active_config_file', None)
    Registry().extend({
      'abc': 123,
      'def': 456
    })
    assertEqual(Registry().abc, 123)
  """
  __metaclass__ = Singleton


def ConcentrateDeferreds(deferred_list):
  """Collects results from list of deferreds.

  CollectDeferreds() returns a deferred object that fires error callback
  on first error. And the original failure won't propagate back to original
  deferred object's next error callback.

  Args:
    deferred_list: Iterable of deferred objects.

  Returns:
    Deferred object that fires error on any deferred_list's errback been
    called. Its callback will be trigged when all callback results are
    collected. The gathered result is a list of deferred object callback
    results.
  """
  return defer.gatherResults(deferred_list, consumeErrors=True)
