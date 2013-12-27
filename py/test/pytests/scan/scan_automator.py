# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'scan' test."""

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import probe
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class ScanAutomator(Automator):
  """The 'scan' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'scan'

  @AutomationFunction(automation_mode=(AutomationMode.PARTIAL,
                                       AutomationMode.FULL))
  def automateScanDefault(self):
    # For scanning MLB serial number.
    if self.args.label_en == 'MLB Serial Number':
      self.uictl.SetElementValue('scan-value', 'TESTMLB')

    # For scanning operator ID.
    elif self.args.label_en == 'Operator ID':
      self.uictl.SetElementValue('scan-value', 'Automation')

    self.uictl.PressKey(self.uictl.KEY_ENTER)

  # TODO(jcliang): Move board-specific logic to configuration file when it's
  # ready.
  @AutomationFunction(boards=['spring'],
                      automation_mode=(AutomationMode.PARTIAL,
                                       AutomationMode.FULL))
  def automateScanForSpring(self):
    # For scanning MLB serial number.
    if self.args.label_en == 'MLB Serial Number':
      probed_results = probe.Probe(
          target_comp_classes=['dram', 'cellular'],
          fast_fw_probe=True,
          probe_volatile=False,
          probe_initial_config=False,
          probe_vpd=False)

      probed_dram = probed_results.found_probe_value_map['dram']
      if isinstance(probed_dram, list):
        probed_dram = probed_dram[0]
      dram_part = probed_dram['part']
      if dram_part.startswith('MT41K256M16HA-125E'):
        memory = 'M'  # Micron
      elif dram_part.startswith('NT5CC256M16BP-DI'):
        memory = 'N'  # Nanya
      else:
        raise ValueError('Unknown dram module probed: %r' %
                         probed_results.found_volatile_values['dram'])

      # Decide test MLB serial number based on the probed results of cellular.
      if 'cellular' in probed_results.missing_component_classes:
        self.uictl.SetElementValue('scan-value', 'TESTMLB-%s-USWIFI' % memory)
      else:
        manufacturer = (
            probed_results.found_probe_value_map['cellular']['manufacturer'])
        if 'Foxconn' in manufacturer or 'Novatel' in manufacturer:
          self.uictl.SetElementValue('scan-value', 'TESTMLB-%s-US3G' % memory)
        elif 'Altair' in manufacturer:
          self.uictl.SetElementValue('scan-value', 'TESTMLB-%s-USLTE' % memory)
        else:
          raise ValueError('Unknown cellular module probed: %r' %
                           probed_results.found_volatile_values['cellular'])

    # For scanning operator ID.
    elif self.args.label_en == 'Operator ID':
      self.uictl.SetElementValue('scan-value', 'Automator')

    self.uictl.PressKey(self.uictl.KEY_ENTER)
