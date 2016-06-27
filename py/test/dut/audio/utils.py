#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.dut.audio import alsa
from cros.factory.test.dut.audio import base
from cros.factory.test.dut.audio import tinyalsa


def CreateAudioControl(dut, config_path=base.DEFAULT_CONFIG_PATH):
  """Creates an AudioControl instance."""
  # Use which to probe audio control class
  # We need to check if all tools required are in the device.
  alsa_commands = ['amixer', 'aplay', 'arecord']
  tinyalsa_commands = ['tinymix', 'tinyplay', 'tinycap']
  if all(dut.Call(['which', command]) == 0 for command in alsa_commands):
    return alsa.AlsaAudioControl(dut, config_path)
  elif all(dut.Call(['which', command]) == 0 for command in tinyalsa_commands):
    return tinyalsa.TinyalsaAudioControl(dut, config_path)
  else:
    raise NotImplementedError
