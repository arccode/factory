# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.utils import type_utils


class MockPlugin(plugin.Plugin):
  @type_utils.Overrides
  def GetUILocation(self):
    return True
