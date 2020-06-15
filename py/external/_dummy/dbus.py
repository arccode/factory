# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dummy implementation for dbus."""

import sys
import types


class DummyClass:
  pass


def DummyFunc(*unused_args, **unused_kargs):
  pass


class Service:
  """Provides dbus.service."""

  class Object:
    pass

  def method(self, *unused_args, **unused_kargs):
    """dbus.service.method, a function decorator."""
    return DummyFunc


service = Service()
DBusException = DummyClass

# Create virtual packages.
_name = 'cros.factory.external.dbus.mainloop'
mainloop = sys.modules[_name] = types.ModuleType(_name)
_name += '.glib'
mainloop.glib = sys.modules[_name] = types.ModuleType(_name)
mainloop.glib.DBusGMainLoop = DummyFunc
