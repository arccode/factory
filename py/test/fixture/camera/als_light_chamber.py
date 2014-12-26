# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import time


# Mock ALS device value.
_ALS_MOCK_VALUE = 10
# Mock ALS scale factor.
_ALS_MOCK_SCALE_FACTOR = 0.5


class ALSLightChamberError(Exception):
  pass


class ALSLightChamber(object):
  """Interfaces the ambient light sensor over iio."""
  # Default min delay seconds.
  _DEFAULT_MIN_DELAY = 0.178

  def __init__(self, val_path, scale_path, fixture_conn, fixture_cmd,
               mock_mode=False):
    """Initializes ALSLightChamber.

    Args:
      fixture_conn: A FixtureConnection instance for controlling the fixture.
      fixture_cmd: A mapping between light name and a list of tuple
                   (cmd, response) required to activate the light.
    """
    self._val_path = val_path
    self._scale_path = scale_path
    self._fixture_conn = fixture_conn
    self._fixture_cmd = fixture_cmd
    self._mock_mode = mock_mode

  def EnableALS(self):
    if self._mock_mode:
      return True

    if (not os.path.isfile(self._val_path) or
        not os.path.isfile(self._scale_path)):
      return False
    return True

  def DisableALS(self):
    pass

  def _ReadCore(self):
    with open(self._val_path, 'r') as f:
      val = int(f.readline().rstrip())
    return val

  def _Read(self, delay=None, samples=1):
    """Reads the light sensor value.

    Args:
      delay: Delay between samples in seconds. 0 means as fast as possible.
      samples: Total samples to read.

    Returns:
      The light sensor values in a list.
    """
    if self._mock_mode:
      return _ALS_MOCK_VALUE

    if samples < 1:
      samples = 1
    if delay is None:
      delay = self._DEFAULT_MIN_DELAY

    buf = []
    # The first value might be contaminated by previous settings.
    # We need to skip it for better accuracy.
    self._ReadCore()
    for _ in range(samples):
      time.sleep(delay)
      val = self._ReadCore()
      buf.append(val)

    return buf

  def ReadMean(self, delay=None, samples=1):
    if self._mock_mode:
      return _ALS_MOCK_VALUE

    buf = self._Read(delay, samples)
    return int(round(float(sum(buf)) / len(buf)))

  def SetScaleFactor(self, scale):
    if self._mock_mode:
      return True

    try:
      with open(self._scale_path, 'w') as f:
        f.write(str(int(round(scale))))
    except Exception:
      return False

    return True

  def GetScaleFactor(self):
    if self._mock_mode:
      return _ALS_MOCK_SCALE_FACTOR

    with open(self._scale_path, 'r') as f:
      s = int(f.readline().rstrip())
    return s

  def SetLight(self, name, response=None):
    """Sets light through fixture connection.

    Args:
      name: name of light specified in fixture_cmd.
    """
    for cmd, response in self._fixture_cmd[name]:
      ret = self._fixture_conn.Send(cmd, response is not None)
      if response and response != ret:
        raise ALSLightChamberError('SetLight: fixture fault')
