# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""ShopFloorHandler: proxys DUT request to factory shop floor backend."""

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import shop_floor_handler as sf


class ShopFloorHandler(sf.ShopFloorHandlerBase):

  @sf.RPCCall
  def GetDeviceInfo(self, mlb_sn):
    if mlb_sn == 'exception':
      raise sf.ShopFloorHandlerException('exception granted.')
    return {'component.has_touchscreen': True}
