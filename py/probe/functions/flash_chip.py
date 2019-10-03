# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess

from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils
from cros.factory.utils import process_utils
from cros.factory.probe.functions import sysfs


MTD_PATH = '/sys/kernel/debug/mtd/mtd0/'

class FlashChipFunction(cached_probe_function.LazyCachedProbeFunction):
  """Get information of flash chips.

  Description
  -----------
  This function runs the command ``flashrom -p <chip_type> --flash-name``
  to get the information of the flash chip and output them.

  The ``<chip_type>`` in above commnand is determind by the ``chip`` argument
  if this function.  Following is a table to show the corresponding
  ``<chip_type>`` value of the specific ``chip`` argument.

  .. list-table::
     :header-rows: 1

     * - Argument ``chip``
       - Corresponding ``<chip_type>``
     * - ``main``
       - ``host``
     * - ``ec``
       - ``ec``
     * - ``pd``
       - ``ec:type=pd``

  Examples
  --------
  Let's assume that the output of ``flashrom -p host --flash-name`` is ::

    vendor="Google"
    name="Chip1"

  And we have the probe statement::

    {
      "eval": "flash_chip:main"
    }

  Then the probed results will be ::

    [
      {
        "vendor": "Google",
        "name": "Chip1"
      }
    ]

  """
  TARGET_MAP = {
      'main': 'host',
      'ec': 'ec',
      'pd': 'ec:type=pd',
  }

  ARGS = [
      Arg('chip', type_utils.Enum(TARGET_MAP),
          'The flash chip. It should be one of {%s}' %
          ', '.join(TARGET_MAP.keys())),
  ]

  def GetCategoryFromArgs(self):
    category = self.TARGET_MAP.get(self.args.chip)
    if not category:
      logging.error('Chip should be one of %s', list(self.TARGET_MAP))
    return category

  @classmethod
  def ProbeDevices(cls, category):
    cmd = ['flashrom', '-p', category, '--flash-name']
    try:
      output = process_utils.CheckOutput(cmd)

    except subprocess.CalledProcessError:
      return function.NOTHING

    # An example of output: vendor="Google" name="Chip1"
    match_list = re.findall(r'\b(\w+)="([^"]*)"', output)
    # In the arm platform, we use the linux MTD driver for the spi
    # nor flash. On the other hand, the flashrom doesn't support
    # the flashinfo query because the linux MTD driver doesn't
    # support it. As a result, we added a debugfs under the MTD_PATH
    # for querying the partid and partname
    if match_list and ('name', 'Opaque flash chip') in match_list:
      result = sysfs.ReadSysfs(MTD_PATH, ['partid', 'partname'])
      if result is not None:
        return result

    return dict(match_list) if match_list else function.NOTHING
