#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.device import component


class Magnetometer(component.DeviceComponent):
  """Base class for magnetometer component module."""

  def __init__(self, board):
    super(Magnetometer, self).__init__(board)

  def GetData(self, capture_count=1, sample_rate=20):
    """Reads several records of raw data and returns the average.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to read data from the sensor.

    Returns:
      A dict of the format {'signal_name': average value}
    """
    raise NotImplementedError
