# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging


class AlgorithmException(Exception):
  pass


class Algorithm:
  """Interface of the computation algorithm."""

  def __init__(self):
    self._logger = logging

  def SetLogger(self, logger):
    self._logger = logger

  def OnStartMoving(self, dut):
    """Callback when the robot is going to move the device.

    Subclass can intialize some sensors here. It can be used to start recording
    a dataset for further computing.

    Raises:
      AlgorithmException if fails to start the process.
    """
    raise NotImplementedError

  def OnStopMoving(self, dut):
    """Callback when the robot is stopped.

    Subclass can implement this function to stop sensors or recording process.

    Raises:
      AlgorithmException if fails.
    """
    raise NotImplementedError

  def Compute(self, dut):
    """Compute after movement.

    This is called after stopping movement. Subclass can implement this function
    to start computing on recording dataset.

    Raises:
      AlgorithmException if fails.
    """
    raise NotImplementedError

  def PullResult(self, dut):
    """Put the result to the target_dir."""
    raise NotImplementedError

  def UploadLog(self, dut, server):
    """Upload log to the factory server."""
    raise NotImplementedError
