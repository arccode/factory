#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect

import factory_common  # pylint: disable=W0611

# Register targets.
from cros.factory.test.dut.links.adb import ADBLink
from cros.factory.test.dut.links.local import LocalLink
from cros.factory.test.dut.links.ssh import SSHLink


KNOWN_LINKS = [ADBLink, LocalLink, SSHLink]
DEFAULT_LINK = LocalLink

def _ExtractArgs(func, kargs):
  spec = inspect.getargspec(func)
  if spec.keywords is None:
    # if the function accepts ** arguments, we can just pass everything into it
    # so we only need to filter kargs if spec.keywords is None
    kargs = {k: v for (k, v) in kargs.iteritems() if k in spec.args}
  return kargs


class DUTLinkOptionsError(Exception):
  """Exception for invalid DUT link options."""
  pass


def GetLinkClass(link_class=None):
  """Returns the class object as specified by the link_class argument.

  Args:
    link_class: A string or class of DUT link instance.
                The string is the full class name in cros.factory.test.dut.link.

  Returns:
    The associated class for creating the right link object, otherwise raises
    DUTLinkOptionsError.
  """
  if link_class is None:
    link_class = DEFAULT_LINK

  # TODO(hungte) Support board-specific link, for example from environment
  # variables just like Board.
  if isinstance(link_class, basestring):
    links = [c for c in KNOWN_LINKS if c.__name__ == link_class]
    if len(links) != 1:
      raise DUTLinkOptionsError('Invalid DUT Link Class <%s>' % link_class)
    link_class = links[0]  # Length of targets was already checked.
  return link_class


def Create(link_class=None, **kargs):
  """Creates a DUT link instance by given options.

  Args:
    link_class: A string or DUTLink subclass . When this is a string,
                it should be the full class name in cros.factory.test.dut.links.
    kargs: The extra parameters passed to DUT link class constructor.
  """
  if link_class is None:
    assert not kargs, 'Arguments cannot be specified without link_class.'
  constructor = GetLinkClass(link_class)
  kargs = _ExtractArgs(constructor.__init__, kargs)
  return constructor(**kargs)


def PrepareLink(link_class=None, **kargs):
  """Prepares a link connection before that kind of link is ready.

  This provides DUT Link to setup system environment for receiving connections,
  especially when using network-based links.

  Args:
    link_class: A string or DUTLink subclass. When this is a string,
                it should be the full class name in cros.factory.test.dut.links.
    kargs: The extra parameters passed to DUT link class constructor.
  """
  if link_class is None:
    assert not kargs, 'Arguments cannot be specified without link_class.'
  class_object = GetLinkClass(link_class)
  kargs = _ExtractArgs(class_object.PrepareLink, kargs)
  return class_object.PrepareLink(**kargs)
