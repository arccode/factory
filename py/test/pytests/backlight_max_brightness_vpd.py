# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to set the maximum brightness value for a panel in vpd.

Since the backlight brightness of a given LCD panel cannot be probed from the
panel in software, we need some way to determine the max brightness of a
panel backlight at run time. As the factory can have knowledge of the panels
being used, we can save the brightness defined for given panels used on a
given device into the VPD. This allows us to have more robust backlight
controls at run time, such as keeping a uniform default brightness across
widely varying panels on a given device.

The test will accept a list of panel identifiers and associated max brightness
values which must be set in the test list, and updated with additional panels
as needed during production.

This test will only fail if allow_unidentified is False, but it will log if it
was unable to set a brightness value for any reason.

Usage examples::

FactoryTest(
    id='BacklightMaxBrightnessVPD',
    label_zh=u'背光最大亮度VPD',
    pytest_name='backlight_max_brightness_vpd',
    dargs={'brightness_values': [('2d04', 'LGD', 250), ('2c13', 'AUO', 200)]})

"""

import logging
import unittest

from cros.factory.gooftool import edid
from cros.factory.system import vpd
from cros.factory.test.args import Arg

class BacklightMaxBrightnessVPDTest(unittest.TestCase):
  """Sets the maximum brighness value in nits to vpd."""
  ARGS = [
    Arg('edid_file', str, 'The file under sysfs to read the EDID',
        optional=True, default='/sys/class/drm/card0-eDP-1/edid'),
    Arg('brightness_values', list, 'Brightness values per panel in a list of '
        'tuples of the form (panel_id, vendor, brightness).', optional=False),
    Arg('vpd_key', str, 'The label to save the value in VPD',
        optional=True, default='panel_backlight_max_nits'),
    Arg('allow_unidentified', bool, 'Allow the test to pass even if a panel '
        'was not identified with a max brightness value', optional=True,
        default=True),
  ]

  def _ReadPanelEDID(self, edid_file):
    """Reads the panel ID from sysfs.

    Args:
      edid_file: The path to the EDID in sysfs.

    Returns:
      The product_id and vendor values from the EDID.
      Returns None, None if the EDID parse fails.
    """
    with open(edid_file) as f:
      parsed_edid = edid.Parse(f.read())
    if parsed_edid is None:
      logging.warning('EDID parsing failed.')
      return None, None
    else:
      return parsed_edid['product_id'], parsed_edid['vendor']

  def runTest(self):
    """Run the test."""
    panel_product_id, panel_vendor = self._ReadPanelEDID(self.args.edid_file)
    max_backlight_nits = None
    for (product_id, vendor, brightness) in self.args.brightness_values:
      if panel_product_id == product_id and panel_vendor == vendor:
        logging.info('Panel %s-%s found.', panel_vendor, panel_product_id)
        max_backlight_nits = brightness
        break
    if max_backlight_nits is not None:
      logging.info('Setting max brightness to %d', max_backlight_nits)
      vpd.ro.Update({self.args.vpd_key: str(max_backlight_nits)})
    else:
      logging.warning('Did not find the panel via EDID, not setting '
                      'a maximum backlight nits value.')
      self.assertTrue(self.args.allow_unidentified, 'The panel must be '
                      'identified to pass this test.')
