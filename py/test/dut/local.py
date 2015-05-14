#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.BaseTarget on local system."""

import shutil
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import base


class LocalTarget(base.BaseTarget):
  """A DUT target that runs locally."""

  def __init__(self):
    """Dummy constructor."""
    pass

  def Push(self, local, remote):
    """See BaseTarget.Push"""
    shutil.copy(local, remote)

  def Pull(self, remote, local=None):
    """See BaseTarget.Pull"""
    if local is None:
      with open(remote) as f:
        return f.read()
    shutil.copy(remote, local)

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See BaseTarget.Shell"""
    return subprocess.call(command, stdin=stdin, stdout=stdout, stderr=stderr,
                           shell=isinstance(command, basestring))

  def IsReady(self):
    """See BaseTarget.IsReady"""
    return True
