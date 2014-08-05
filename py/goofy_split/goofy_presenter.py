#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the presenter-side of factory tests."""

import logging
import subprocess
import syslog

import factory_common  # pylint: disable=W0611
from cros.factory.goofy_split.goofy_base import GoofyBase
from cros.factory.goofy_split.link_manager import DUTLinkManager
from cros.factory.goofy_split.ui_app_controller import UIAppController
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
  """
  def __init__(self):
    super(GoofyPresenter, self).__init__()
    self.ui_app_controller = UIAppController()
    self.ui_app_controller.WaitForWebSocket()

    # We are skipping the login UI, so we need to emit login-prompt-visible
    # event here so as to notify upstart jobs to continue.  However, if we
    # are not running on Chrome OS device, we don't want to do this.
    if utils.in_cros_device():
      subprocess.check_call(['initctl', 'emit', 'login-prompt-visible'])

    self.link_manager = DUTLinkManager(
        check_interval=1,
        connect_hook=self.DUTConnected,
        disconnect_hook=self.DUTDisconnected)

  def DUTConnected(self, dut_ip):
    self.ui_app_controller.ShowUI(dut_ip)

  def DUTDisconnected(self):
    self.ui_app_controller.ShowDisconnectedScreen()

  def main(self):
    """Entry point for goofy_presenter instance."""
    syslog.openlog('goofy_presenter')
    syslog.syslog('GoofyPresenter (factory test harness) starting')
    self.run()

  def destroy(self):
    """ Performs any shutdown tasks. Overrides base class method. """
    self.link_manager.Stop()
    self.ui_app_controller.Stop()
    super(GoofyPresenter, self).destroy()
    logging.info('Done destroying GoofyPresenter')


if __name__ == '__main__':
  goofy = GoofyPresenter()
  try:
    goofy.main()
  except SystemExit:
    # Propagate SystemExit without logging.
    raise
  except:
    # Log the error before trying to shut down (unless it's a graceful
    # exit).
    logging.exception('Error in main loop')
    raise
  finally:
    goofy.destroy()
