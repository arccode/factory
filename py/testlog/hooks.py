# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Testlog event hooks."""

class Hooks(object):
  """Testlog event hooks.

  This class is a dummy implementation, but methods may be overridden by the
  subclass.
  """

  def OnStationInit(self, event):
    """Invoked on every station.init event."""
    pass

  def OnStationMessage(self, event):
    """Invoked on every station.message event."""
    pass

  def OnStationTestRun(self, event):
    """Invoked on every station.test_run event."""
    pass
