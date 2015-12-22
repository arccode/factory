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
  if dut.Call(['which', 'amixer']) == 0:
    return alsa.AlsaAudioControl(dut, config_path)
  elif dut.Call(['which', 'tinymix']) == 0:
    return tinyalsa.TinyalsaAudioControl(dut, config_path)
  else:
    raise NotImplementedError
