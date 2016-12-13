# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
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

  def __init__(self, dut, val_path, scale_path, fixture_conn, fixture_cmd,
               mock_mode=False, retries=3):
    """Initializes ALSLightChamber.

    Args:
      fixture_conn: A FixtureConnection instance for controlling the fixture.
      fixture_cmd: A mapping between light name and a list of tuple
                   (cmd, response) required to activate the light.
    """
    self._dut = dut
    self._val_path = val_path
    self._scale_path = scale_path
    self._fixture_conn = fixture_conn
    self._fixture_cmd = fixture_cmd
    self._mock_mode = mock_mode
    self._retries = retries

  def Connect(self):
    self._fixture_conn.Connect()

  def EnableALS(self):
    if self._mock_mode:
      return True

    if self._dut.Shell(['test', '-e', self._val_path]):
      logging.info('ALS val_path does not exist')
      return False

    # Some drivers do not support setting/getting calibration scale. in such
    # case we can still work with it, but GetScaleFactor/SetScaleFactor is
    # not supported.
    if self._scale_path is None:
      logging.info('ALS scaling is not supported')
    elif self._dut.Shell(['test', '-e', self._scale_path]):
      # The user specified scale path, but it does not exist.
      logging.info('ALS scale_path does not exist')
      return False

    return True

  def DisableALS(self):
    pass

  def _ReadCore(self):
    return int(self._dut.Pull(self._val_path).rstrip())

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

    if self._scale_path is None:
      raise RuntimeError('ALS scaling is not supported')

    try:
      self._dut.Shell('echo %d >%s' % (int(round(scale)), self._scale_path))
    except Exception:
      return False

    return True

  def GetScaleFactor(self):
    if self._mock_mode:
      return _ALS_MOCK_SCALE_FACTOR

    if self._scale_path is None:
      raise RuntimeError('ALS scaling is not supported')

    return int(self._dut.Pull(self._scale_path).rstrip())

  def SetLight(self, name, response=None):
    """Sets light through fixture connection.

    Args:
      name: name of light specified in fixture_cmd.
    """
    for unused_i in range(self._retries):
      for cmd, response in self._fixture_cmd[name]:
        ret = self._fixture_conn.Send(cmd, True)
        if response is None or ret.strip() == response:
          return

    raise ALSLightChamberError('SetLight: fixture fault')
