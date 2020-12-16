# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import time

from chromite.lib.firmware.flash_ap import DutControl


SERVOD_BIN = '/usr/bin/servod'
SERVOD_INIT_SEC = 1
SERVOD_KILL_TIMEOUT_SEC = 3


class Servod:
  """Run servod and get the interface to execute dut-control commands.

  Args:
    port: The port to run servod.
    board: The board argument of servod. The addition board configuration will
    be loaded.
    serial_name: The serial_name argument of servod. It is necessary if there
    are multiple servo connections.
  """

  def __init__(self, port=9999, board=None, serial_name=None):
    self._port = port
    self._board = board
    self._serial_name = serial_name
    self._servod = None

  def _CheckServodAlive(self):
    if self._servod.poll() is not None:
      raise RuntimeError('Servod unexpectedly stopped.')

  def __enter__(self):
    """Start servod and wait for it being ready.

    Returns:
      A DutControl interface object to execute dut-control commands.
    """
    servod_cmd = [SERVOD_BIN, '-p', str(self._port)]
    if self._board:
      servod_cmd += ['-b', self._board]
    if self._serial_name:
      servod_cmd += ['-s', self._serial_name]

    self._servod = subprocess.Popen(servod_cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
    # Wait for servod to be ready for communicating with dut-control.
    time.sleep(SERVOD_INIT_SEC)
    self._CheckServodAlive()
    return DutControl(self._port)

  def __exit__(self, *args, **kargs):
    """Stop servod. Force stop it if it doesn't stop after timeout."""
    if self._servod.poll() is not None:
      return
    self._servod.terminate()
    try:
      self._servod.wait(SERVOD_KILL_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
      self._servod.kill()
