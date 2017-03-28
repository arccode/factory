# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from __future__ import print_function

import inspect

import factory_common  # pylint: disable=unused-import
from cros.factory.shopfloor import factory_update_server


class FactoryUpdater(factory_update_server.FactoryUpdateServer):
  """A dummy FactoryUpdater.

  This behaves like the one started in shopfloor.ShopFloorBase, but without
  starting the rsync daemon.

  This is intended to be used in unittest only.
  """
  def __init__(self, *args, **kwargs):
    kwargs.update({'rsyncd_addr': None})
    super(FactoryUpdater, self).__init__(*args, **kwargs)

  def Start(self):
    if self._thread is None:
      instance = inspect.currentframe().f_back.f_locals['self']
      self.on_idle = instance._AutoSaveLogs  # pylint: disable=protected-access
      super(FactoryUpdater, self).Start()

  def Stop(self):
    if self._thread is not None:
      super(FactoryUpdater, self).Stop()
