# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class FlashChipFunction(function.ProbeFunction):
  """Get information of flash chip."""
  TARGET_MAP = {
      'main': 'host',
      'ec': 'ec',
      'pd': 'ec:type=pd',
  }

  ARGS = [
      Arg('chip', str,
          'The flash chip. It should be one of {%s}' %
          ', '.join(TARGET_MAP.keys())),
  ]

  def Probe(self):
    if self.args.chip not in self.TARGET_MAP:
      logging.error('Chip should be one of %s', self.TARGET_MAP.keys())
      return function.NOTHING

    cmd = ['flashrom', '-p', self.TARGET_MAP[self.args.chip], '--flash-name']
    try:
      output = process_utils.CheckOutput(cmd)
    except subprocess.CalledProcessError:
      return function.NOTHING

    # An example of output: vendor="Google" name="Chip1"
    match_list = re.findall(r'\b(\w+)="([^"]*)"', output)
    return dict(match_list) if match_list else function.NOTHING
