# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common classes and helpers acrosss RF stuff."""

class Frequency:
  """Class that represents a specific frequency."""

  _f = None

  def __init__(self, f):
    """Initialize a frequency instance. f must be convertable to float in Hz."""
    self._f = float(f)

  def __repr__(self):
    """Returns a string representation."""
    return 'Frequency(%f Hz)' % self._f

  @staticmethod
  def FromHz(f):
    """Return an f Hz frequency instance."""
    return Frequency(f)

  @staticmethod
  def FromKHz(f):
    """Return an f KHz frequency instance."""
    return Frequency(1e3 * float(f))

  @staticmethod
  def FromMHz(f):
    """Return an f MHz frequency instance."""
    return Frequency(1e6 * float(f))

  @staticmethod
  def FromGHz(f):
    """Return an f GHz frequency instance."""
    return Frequency(1e9 * float(f))

  def Hzf(self):
    """Return frequency in Hz (float)."""
    return self._f

  def KHzf(self):
    """Return frequency in KHz (float)."""
    return self._f / 1e3

  def MHzf(self):
    """Return frequency in MHz (float)."""
    return self._f / 1e6

  def GHzf(self):
    """return frequency in GHz (float)."""
    return self._f / 1e9

  def Hzi(self):
    """Return frequency in Hz (integer), may lose precision."""
    return int(self._f)

  def KHzi(self):
    """Return frequency in KHz (integer), may lose precision."""
    return int(self._f / 1e3)

  def MHzi(self):
    """Return frequency in MHz (integer), may lose precision."""
    return int(self._f / 1e6)

  def GHzi(self):
    """return frequency in GHz (integer), may lose precision."""
    return int(self._f / 1e9)
