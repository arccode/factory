#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the presenter-side of factory tests."""

import argparse
import logging
import syslog

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import test_environment
from cros.factory.goofy.goofy_base import GoofyBase
from cros.factory.goofy.link_manager import DUTLinkManager
from cros.factory.goofy.ui_app_controller import UIAppController
from cros.factory.test import utils

class GoofyPresenter(GoofyBase):
  """Presenter side of Goofy.

  Note that all methods in this class must be invoked from the main
  (event) thread.  Other threads, such as callbacks and TestInvocation
  methods, should instead post events on the run queue.

  Properties:
    link_manager: The DUTLinkManager for this invocation of Goofy.
    ui_app_controller: UIAppController instance used to communicate with
        UI presenter app.
    dut_ip: The last known IP address of the DUT. None if a DUT is never seen.
  """
  def __init__(self):
    super(GoofyPresenter, self).__init__()

    self.args = self.ParseOptions()

    self.ui_app_controller = UIAppController(connect_hook=self.UIConnected)
    self.dut_ip = None
    self.dut_uuid = None

    if utils.in_cros_device():
      self.env = test_environment.DUTEnvironment()
      self.env.has_sockets = self.ui_app_controller.HasWebSockets
    else:
      self.env = test_environment.FakeChrootEnvironment()
    self.env.launch_chrome()

    self.link_manager = DUTLinkManager(
        check_interval=1,
        connect_hook=self.DUTConnected,
        disconnect_hook=self.DUTDisconnected,
        methods={'StartCountdown': self.UIAppCountdown},
        standalone=self.args.standalone)

  def ParseOptions(self):
    parser = argparse.ArgumentParser(description="Run Goofy presenter")
    parser.add_argument('--standalone', action='store_true',
                        help=('Assume the controller is running on the same '
                              'machines.'))
    return parser.parse_args()

  def DUTConnected(self, dut_ip):
    self.dut_uuid = self.link_manager.GetUuid()
    self.dut_ip = dut_ip
    self.ui_app_controller.ShowUI(dut_ip, dut_uuid = self.dut_uuid)

  def DUTDisconnected(self):
    self.ui_app_controller.ShowDisconnectedScreen()
    self.dut_ip = None

  def UIConnected(self):
    if self.dut_ip:
      self.ui_app_controller.ShowUI(self.dut_ip, dut_uuid=self.dut_uuid)

  def UIAppCountdown(self, message, timeout_secs, timeout_message,
                     timeout_message_color):
    """Start countdown on the UI.

    Args:
      message: The text to show during countdown.
      timeout_secs: The timeout for countdown.
      timeout_message: The text to show when countdown eneds.
      timeout_message_color: The color of the text when countdown ends.
    """
    self.ui_app_controller.StartCountdown(message, timeout_secs,
                                          timeout_message,
                                          timeout_message_color)

  def main(self):
    """Entry point for goofy_presenter instance."""
    syslog.openlog('goofy_presenter')
    syslog.syslog('GoofyPresenter (factory test harness) starting')
    self.run()

  def destroy(self):
    """Performs any shutdown tasks. Overrides base class method."""
    self.link_manager.Stop()
    self.ui_app_controller.Stop()
    super(GoofyPresenter, self).destroy()
    logging.info('Done destroying GoofyPresenter')


if __name__ == '__main__':
  GoofyPresenter.run_main_and_exit()
