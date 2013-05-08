# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides an interface for DUT to interact with BFT fixture."""

class BFTFixtureException(Exception):
  pass

class BFTFixtureBase(object):
  """Base class of BFT (Board Function Test) fixture.

  It defines interfaces for DUT (Device Under Test) to interact with
  BFT fixture.
  """

  # Enums for ScanLED's return value.
  LED_RED = 0
  LED_GREEN = 1
  LED_AMBER = 2

  def Handshake(self):
    """Returns True if BFT can communicate with DUT well."""
    raise NotImplementedError

  def GetFixtureId(self):
    """Returns a fixture ID."""
    raise NotImplementedError

  def ScanKeyboard(self):
    """Triggers keyboard keycode scanner."""
    raise NotImplementedError

  def CloseLid(self):
    """Activates a electromagnet in BFT to simulate lid close."""
    raise NotImplementedError

  def OpenLid(self):
    """Deactivates a electromagnet in BFT to simulate lid open."""
    raise NotImplementedError

  def PlugAudioLoopback(self):
    """Plugs a loopback dongle into headphone/mic jack."""
    raise NotImplementedError

  def UnplugAudioLoopback(self):
    """Unplugs the loopback dongle from headphone/mic jack."""
    raise NotImplementedError

  def LightLED(self, color):
    """Turns on on-board LED with color specified."""
    raise NotImplementedError

  def ScanLED(self):
    """Returns the color seen by fixture's LED sensor."""
    raise NotImplementedError

  def ScanBarcode(self):
    """Triggers a barcode scanner in BFT."""
    raise NotImplementedError

  def PlugAC(self):
    """Plugs AC power."""
    raise NotImplementedError

  def UnplugAC(self):
    """Unplugs AC power."""
    raise NotImplementedError

  def PlugUSB(self, port):
    """Plugs a USB disk into the specified port."""
    raise NotImplementedError

  def UnplugUSB(self, port):
    """Unplugs a USB disk from the specified port."""
    raise NotImplementedError

  def PlugExtDisplay(self):
    """Plugs in external display."""
    raise NotImplementedError

  def UnplugExtDisplay(self):
    """Unplugs external display."""
    raise NotImplementedError
