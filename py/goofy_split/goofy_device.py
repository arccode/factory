#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the device-side of factory tests."""

import logging
import syslog

import factory_common  # pylint: disable=W0611
from cros.factory.goofy_split.goofy_base import GoofyBase
from cros.factory.goofy_split.link_manager import HostLinkManager

class GoofyDevice(GoofyBase):
  """Device side of Goofy.

  Note that all methods in this class must be invoked from the main
  (event) thread.  Other threads, such as callbacks and TestInvocation
  methods, should instead post events on the run queue.

  Properties:
    link_manager: The HostLinkManager for this invocation of Goofy.
  """
  def __init__(self):
    super(GoofyDevice, self).__init__()
    self.link_manager = HostLinkManager(check_interval=1)

  def main(self):
    """Entry point for goofy_device instance."""
    syslog.openlog('goofy_device')
    syslog.syslog('GoofyDevice (factory test harness) starting')
    self.run()

  def destroy(self):
    """ Performs any shutdown tasks. Overrides base class method. """
    self.link_manager.Stop()
    super(GoofyDevice, self).destroy()
    logging.info('Done destroying GoofyDevice')


if __name__ == '__main__':
  goofy = GoofyDevice()
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
