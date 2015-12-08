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
from cros.factory.test.dut.ssh import SSHTarget


KNOWN_TARGETS = [AdbTarget, LocalTarget, SSHTarget]
DEFAULT_TARGET = LocalTarget


class OptionsError(Exception):
  pass


def GetClass(dut_class=None):
  if dut_class is None:
    dut_class = DEFAULT_TARGET
  if isinstance(dut_class, basestring):
    targets = [c for c in KNOWN_TARGETS if c.__name__ == dut_class]
    if len(targets) != 1:
      raise OptionsError('Invalid DUT class <%s>' % dut_class)
    dut_class = targets[0]  # Length of targets was already checked.
  return dut_class


def Create(dut_class=None, **dut_options):
  """Creates a DUT instance by given options.

  Args:
    dut_class: A string or class of DUT instance.
               The string is the full class name in cros.factory.test.dut.
    kargs: The extra parameters passed to DUT class constructor.
  """
  if dut_class is None:
    assert not dut_options, 'Arguments cannot be specified without dut_class.'

  constructor = GetClass(dut_class)
  return constructor(**dut_options)


def PrepareConnection(dut_class=None, **dut_options):
  dut_class = GetClass(dut_class)
  dut_class.PrepareConnection(**dut_options)
