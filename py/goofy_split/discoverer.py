#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils


class DiscovererBase(object):
  """Base class for discoverers."""
  def Discover(self):
    """Returns IP addresses of the potential host/DUT."""
    raise NotImplementedError()


class DUTDiscoverer(DiscovererBase):
  """Discoverer that looks for the DUT."""
  def Discover(self):
    if utils.in_chroot():
      return '127.0.0.1'
    else:
      # For now, we assume the host and the device are the same
      # machine.
      # TODO: implement this
      return '127.0.0.1'


class HostDiscoverer(DiscovererBase):
  """Discoverer that looks for the host."""
  def Discover(self):
    if utils.in_chroot():
      return '127.0.0.1'
    else:
      # For now, we assume the host and the device are the same
      # machine.
      # TODO: implement this
      return '127.0.0.1'
