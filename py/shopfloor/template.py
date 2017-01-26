# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""(CHANGE THIS) This is a template for creating new implementation of factory shop floor system module.
"""


# Add required python modules here.
import logging

# Always include 'shopfloor' for the abstract base class.
import factory_common  # pylint: disable=W0611
from cros.factory import shopfloor


class ShopFloor(shopfloor.ShopFloorBase):
  """(CHANGE THIS) Implementation for factory shop floor system."""
  NAME = '(CHANGE THIS) Shopfloor system template'
  VERSION = 1

  def __init__(self, config=None):
    """See help(ShopFloorBase.__init__)"""
    super(ShopFloor, self).__init__()
    self.config = config
    logging.info('Shop floor system started.')

  def Finalize(self, serial):
    """See help(ShopFloorBase.Finalize)"""
    raise NotImplementedError('Finalize')
