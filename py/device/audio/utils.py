# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device.audio import alsa
from cros.factory.device.audio import tinyalsa
from cros.factory.utils import type_utils


# Known controllers.
CONTROLLERS = type_utils.Enum(['ALSA', 'TINYALSA'])


def CreateAudioControl(dut, config_path=None, controller=None):
  """Creates an AudioControl instance.

  Args:
    dut: a DUT instance to be passed into audio component.
    config_path: a string of file path to config file to load.
    controller: a string for the audio system to use.
  """
  controllers = {
      CONTROLLERS.ALSA: alsa.AlsaAudioControl,
      CONTROLLERS.TINYALSA: tinyalsa.TinyalsaAudioControl
  }
  constructor = None

  if controller is None:

    # Auto-detect right controller..
    alsa_commands = ['amixer', 'aplay', 'arecord']
    tinyalsa_commands = ['tinymix', 'tinyplay', 'tinycap']

    if all(dut.Call(['which', command]) == 0 for command in alsa_commands):
      controller = CONTROLLERS.ALSA
    if all(dut.Call(['which', command]) == 0 for command in tinyalsa_commands):
      controller = CONTROLLERS.TINYALSA

  # Read from controllers.
  constructor = controllers.get(controller)

  if constructor is None:
    raise NotImplementedError

  return constructor(dut, config_path)
