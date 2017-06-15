# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Bridge to Shopfloor Service."""

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.service import umpire_service


class ShopfloorService(umpire_service.UmpireService):
  """Shopfloor service (dummy version)."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config  # unused
    del env  # unused
    return ()
