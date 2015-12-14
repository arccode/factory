#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.link.DUTLink on local system."""

import shutil
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import link


class LocalLink(link.DUTLink):
  """Runs locally on a DUT."""

  def __init__(self):
    """Dummy constructor."""
    pass

  def Push(self, local, remote):
    """See DUTLink.Push"""
    shutil.copy(local, remote)

  def Pull(self, remote, local=None):
    """See DUTLink.Pull"""
    if local is None:
      with open(remote) as f:
        return f.read()
    shutil.copy(remote, local)

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See DUTLink.Shell"""
    return subprocess.call(command, stdin=stdin, stdout=stdout, stderr=stderr,
                           shell=isinstance(command, basestring))

  def IsReady(self):
    """See DUTLink.IsReady"""
    return True

  def IsLocal(self):
    """See DUTLink.IsLocal"""
    return True
