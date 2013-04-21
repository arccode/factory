# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.schema import FixedDict, Dict, Scalar, List
from cros.factory.shopfloor.launcher import constants


class LauncherYAMLConfig(dict):
  """ShopFloor Launcher YAML config file validator."""

  _SCHEMA = FixedDict(
      'Fixed top level launcher config fields',
      optional_items={
          # Network installer settings.
          'network_install': FixedDict(
              'network_install_fields',
              items={
                'port': Scalar('Network download port', int),
                'board': Dict(
                    'boards',
                    Scalar('Board name', str),
                    FixedDict(
                        'Resources for the board',
                        items={
                            'config': Scalar('download_conf', str),
                            'efi': Scalar('EFI partition image', str),
                            'firmware': Scalar('Firmware updater', str),
                            'hwid': Scalar('HWID resource', str),
                            'oem': Scalar('OEM partition image', str),
                            'rootfs-release': Scalar(
                                'Release rootfs and Kernel',
                                 str),
                            'rootfs-test': Scalar(
                                'Factory test rootfs and Kernel',
                                str),
                            'state': Scalar('Stateful partition image', str)},
                        optional_items={
                            'complete': Scalar(
                                'Complete script to run after download',
                                str)}))},
                optional_items={
                  'netboot_kernel': Scalar('Network tftp boot uImage', str),
                  'dhcp': FixedDict(
                      'DHCP server settings',
                      items={
                          'interface': List('Interface list',
                                            Scalar('Ethernet interface', str)),
                          'subnet': Scalar('DHCP subnet', str),
                          'netmask': Scalar('Subnet netmask', str),
                          'range': List('DHCP range, start IP and end IP',
                                        Scalar('IP address', str))})})},
      items={
          # Info fields includes version and note. Both fields are human
          # readable one-line strings for command line utility to display.
          'info': FixedDict(
              'Human readable info strings',
              items={'version': Scalar('Factory bundle version', str)},
              optional_items={'note': Scalar('One line note for this release',
                                             str)}),

          # Base ShopFloor configurations, includes factory.par resource, the
          # module resource for factory integration and the http daemon bind
          # port.
          'shopfloor': FixedDict(
              'ShopFloor software configuration',
              items={
                  'factory_software': Scalar('Factory software par file', str),
                  'shopfloor_module': Scalar('Shopfloor factory module', str)},
              optional_items={
                  'port': Scalar('Shopfloor HTTPD front end port number',
                                 int)})})

  def __init__(self, config_file):
    with open(config_file, 'r') as f:
      launcher_config = yaml.load(f)
      self._SCHEMA.Validate(launcher_config)
      if 'port' not in launcher_config['shopfloor']:
        launcher_config['shopfloor']['port'] = (
            constants.DEFAULT_BIND_PORT)
      super(LauncherYAMLConfig, self).__init__(launcher_config)

