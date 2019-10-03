# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Bridge to Chrome OS Factory Shopfloor Service.

The proxy is current implemented in server/dut_rpc.py so this service is now
simply a dummy implementation for holding config.
"""

from cros.factory.umpire.server.service import umpire_service


class ShopFloorService(umpire_service.UmpireService):
  """Shop floor service."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config  # unused
    del env  # unused
    return ()
