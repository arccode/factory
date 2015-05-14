#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611

# Register targets.
from cros.factory.test.dut.adb import AdbTarget
from cros.factory.test.dut.base import BaseTarget
from cros.factory.test.dut.local import LocalTarget
from cros.factory.test.dut.ssh import SshTarget


KNOWN_TARGETS = [AdbTarget, LocalTarget, SshTarget]
DEFAULT_TARGET = LocalTarget


class OptionsError(Exception):
  pass


def Create(dut_class=None, **kargs):
  """Creates a DUT instance by given options.

  Args:
    dut_class: A string or class of DUT instance.
               The string is the full class name in cros.factory.test.dut.
    kargs: The extra parameters passed to DUT class constructor.
  """
  if dut_class is None:
    assert not kargs, 'Arguments cannot be specified without dut_class.'
    dut_class = DEFAULT_TARGET

  if isinstance(dut_class, basestring):
    targets = [c for c in KNOWN_TARGETS if c.__name__ == dut_class]
    if len(targets) != 1:
      raise OptionsError('Invalid DUT class <%s>' % dut_class)
    constructor = targets[0]  # Length of targets was already checked.
  else:
    constructor = dut_class

  return constructor(**kargs)
