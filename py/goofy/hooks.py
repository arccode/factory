#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils import sys_utils


class Hooks(object):
  """Goofy hooks.

  This class is a dummy implementation, but methods may be overridden
  by the subclass.

  Properties (initialized by Goofy):
    test_list: The test_list object.
  """
  test_list = None

  def OnStartup(self):
    """Invoked on Goofy startup (just before the UI is started)."""
    pass

  def OnCreatedTestList(self):
    """Invoked right after Goofy creates test_list."""
    pass

  def OnTestStart(self):
    """Callback invoked a factory test starts.

    This method is called when goofy starts or when the operator
    starts a test manually. This can be used to light up a green
    LED or send a notification to a remote server.
    """
    pass

  def OnTestFailure(self, test):
    """Callback invoked when a test fails.

    This method can be used to bring the attention of the operators
    when a display is not available. For example, lighting up a red
    LED may help operators identify failing device on the run-in
    rack easily.
    """
    pass

  def OnEvent(self, event_name, *args, **kargs):
    """A general handler for events to Goofy hooks.

    This method can be used by pytests to trigger some customized hooks,
    for example to notify the operator if a device has finished a test section,
    e.g. run-in.

    A real use case is 'SummaryGood' event for lighting up a green LED here and
    the operators may be instructed to move all devices with a green LED to FATP
    testing; 'SummaryBad' if the summary test founds failure.
    """
    logging.info('Goofy hook event: %s%r%r', event_name, args, kargs)

  def OnUnexpectedReboot(self):
    """Callback invoked after the device experiences an unexpected reboot."""
    logging.info(sys_utils.GetStartupMessages(
        device_utils.CreateDUTInterface()))


