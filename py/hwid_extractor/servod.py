# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import time


SERVOD_BIN = '/usr/bin/servod'
SERVOD_INIT_SEC = 1
SERVOD_KILL_TIMEOUT_SEC = 3


class DutControl:
  """Alernative implementation of DutControl in chromite/lib/firmware/flash_ap

  `flash_ap.py` has too many dependencies which are not used by us.
  Reimplementing this reduces the unused dependencies.
  TODO(chungsheng): Refactor chromite/lib/firmware/flash_ap.py for better
  reusability.
  """

  def __init__(self, port):
    self._base_cmd = ['dut-control']
    if port:
      self._base_cmd.append('--port=%s' % port)

  def get_value(self, arg):
    """Get the value of |arg| from dut_control."""
    return subprocess.check_output(self._base_cmd + ['--value_only', arg],
                                   encoding='utf-8').strip()

  def run(self, cmd_fragment):
    """Run a dut_control command.

    Args:
      cmd_fragment (list[str]): The dut_control command to run.
    """
    subprocess.check_call(self._base_cmd + cmd_fragment)

  def run_all(self, cmd_fragments):
    """Run multiple dut_control commands in the order given.

    Args:
      cmd_fragments (list[list[str]]): The dut_control commands to run.
    """
    for cmd in cmd_fragments:
      self.run(cmd)


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
