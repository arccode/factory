# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.probe.lib import cached_probe_function


RESULT_KEY = 'name'


class GenericAudioCodecFunction(cached_probe_function.CachedProbeFunction):
  """Probe the generic audio codec information."""

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    """Looks for codec strings.

    Collect /sys/kernel/debug/asoc/codecs for ASOC (ALSA SOC) drivers,
    /proc/asound for HDA codecs, then PCM details.

    There is a set of known invalid codec names that are not included in the
    return value.
    """
    KNOWN_INVALID_CODEC_NAMES = set([
        'snd-soc-dummy',
        'dw-hdmi-audio'  # this is a virtual audio codec driver
    ])

    results = []
    asoc_paths = [
        '/sys/kernel/debug/asoc/codecs', # for kernel version <= 4.4
        '/sys/kernel/debug/asoc/components', # for kernel version >= 4.14
    ]
    for p in asoc_paths:
      if os.path.exists(p):
        with open(p) as f:
          results.extend([codec.strip()
                          for codec in f.read().splitlines()
                          if codec not in KNOWN_INVALID_CODEC_NAMES])
    return [{RESULT_KEY: result} for result in results]
