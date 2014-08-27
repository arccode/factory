# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for modifying factory bundle."""

import glob
import logging
import os
import re
import shutil
import urlparse

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, bundle_dir_cmd_arg, FactoryFlowCommand)
from cros.factory.hacked_argparse import CmdArg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


class ModifyBundleError(Exception):
  """Modify bundle error."""
  pass


class ModifyBundle(FactoryFlowCommand):
  """Modifies settings of an existing factory bundle.

  The subcommand currently supports updating mini-omaha IP address and port in
  the following places inside the factory bundle:

  - MANIFEST.yaml
  - lsb_factory file in install shim
  - firmware variables in either uboot or depthcharge netboot firmware.
  """
  args = [
      board_cmd_arg,
      bundle_dir_cmd_arg,
      CmdArg('--mini-omaha-ip', required=True,
             help=('IP address of the mini omaha server; set this to None to '
                   'rely on DHCP server to provide the IP address')),
      CmdArg('--mini-omaha-port', type=int,
             help='port of the mini omaha server (default: %(default)s)',
             default=8080),
  ]

  def UpdateManifest(self, mini_omaha_url):
    """Updates mini_omaha_url in MANIFEST.yaml.

    Args:
      mini_omaha_url: The mini-omaha URL to patch.
    """
    manifest_path = os.path.join(self.options.bundle, 'MANIFEST.yaml')
    if not os.path.isfile(manifest_path):
      raise ModifyBundleError('Unable to find MANIFEST.yaml in %s' %
                              self.options.bundle)
    with open(manifest_path) as f:
      manifest = f.read()
    # The mini_omaha_url field to write to the manifest.
    mini_omaha_url_field = 'mini_omaha_url: %s' % mini_omaha_url
    # Update or add mini_omaha_url field.
    mini_omaha_url_regexp = re.compile(r'^mini_omaha_url:\s+.+\s*$',
                                       re.MULTILINE)
    if not mini_omaha_url_regexp.search(manifest):
      logging.warn('Original MANIFEST.yaml does not have mini_omaha_url field')
      updated_manifest = manifest + ('\n%s\n' % mini_omaha_url_field)
    else:
      updated_manifest = mini_omaha_url_regexp.sub(
          mini_omaha_url_field, manifest)
    with open(manifest_path, 'w') as f:
      f.write(updated_manifest)

  def UpdateInstallShim(self, mini_omaha_url):
    """Updates mini_omaha_url in install shim.

    It also updates self.install_shim_version.

    Args:
      mini_omaha_url: The mini-omaha URL to patch.
    """
    def PatchLSBFactory(mount, mini_omaha_url):
      """Patches lsb-factory in an image.

      Args:
        mount: The mount point.
        mini_omaha_url: The mini-omaha URL to patch.
      """
      lsb_factory_path = os.path.join(
          mount, 'dev_image', 'etc', 'lsb-factory')
      logging.info('Patching URLs in %s', lsb_factory_path)
      orig_lsb_factory = open(lsb_factory_path).read()
      lsb_factory, number_of_subs = re.subn(
          '(?m)^(CHROMEOS_(AU|DEV)SERVER=).+$', r'\1' + mini_omaha_url,
          orig_lsb_factory)
      if number_of_subs != 2:
        raise ModifyBundleError(
            'Unable to set mini-Omaha server in %s' % lsb_factory_path)
      file_utils.WriteWithSudo(lsb_factory_path, lsb_factory)

    # Patch in the install shim, if present.
    has_install_shim = False
    unsigned_shim = os.path.join(self.options.bundle, 'factory_shim',
                                 'factory_install_shim.bin')
    if os.path.isfile(unsigned_shim):
      with sys_utils.MountPartition(unsigned_shim, 1, rw=True) as mount:
        PatchLSBFactory(mount, mini_omaha_url)
      has_install_shim = True

    signed_shims = (
        glob.glob(
            os.path.join(
                self.options.bundle, 'factory_shim',
                'chromeos_*_factory*.bin')))
    if has_install_shim and signed_shims:
      raise ModifyBundleError('Both unsigned and signed install shim exists. '
                              'Please remove unsigned one')
    if len(signed_shims) > 1:
      raise ModifyBundleError(
          'Expected to find 1 signed factory shim but found %d: %r' % (
              len(signed_shims), signed_shims))
    elif len(signed_shims) == 1:
      with sys_utils.MountPartition(signed_shims[0], 1, rw=True) as mount:
        PatchLSBFactory(mount, mini_omaha_url)
      has_install_shim = True

    if not has_install_shim:
      logging.warning('There is no install shim in the bundle.')

  def UpdateUbootNetboot(self, mini_omaha_url):
    """Updates Omaha & TFTP servers' URL in uboot netboot firmware.

    Args:
      mini_omaha_url: The mini-omaha URL to patch.
    """
    netboot_firmware_image = os.path.join(
        self.options.bundle, 'netboot_firmware',
        'nv_image-%s.bin' % self.options.board.short_name)
    if os.path.exists(netboot_firmware_image):
      update_firmware_vars = os.path.join(
          self.options.bundle, 'factory_setup', 'update_firmware_vars.py')
      new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
      process_utils.Spawn([
          update_firmware_vars,
          '--force',
          '-i', netboot_firmware_image,
          '-o', new_netboot_firmware_image,
          '--omahaserver=%s' % mini_omaha_url,
          '--tftpserverip=%s' %
          urlparse.urlparse(mini_omaha_url).hostname],
                          check_call=True, log=True)
      shutil.move(new_netboot_firmware_image, netboot_firmware_image)

  def UpdateDepthchargeNetboot(self, mini_omaha_url):
    """Updates Omaha & TFTP servers' URL in depthcharge netboot firmware.

    Args:
      mini_omaha_url: The mini-omaha URL to patch.
    """
    netboot_firmware_image = os.path.join(
        self.options.bundle, 'netboot_firmware', 'image.net.bin')
    if os.path.exists(netboot_firmware_image):
      update_firmware_settings = (
          os.path.join(
              self.options.bundle, 'factory_setup',
              'update_firmware_settings.py'))
      new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
      process_utils.Spawn([update_firmware_settings,
                           '--bootfile', 'vmlinux.bin',
                           '--input', netboot_firmware_image,
                           '--output', new_netboot_firmware_image,
                           '--omahaserver=%s' % mini_omaha_url,
                           '--tftpserverip=%s' %
                           urlparse.urlparse(mini_omaha_url).hostname],
                          check_call=True, log=True)
      shutil.move(new_netboot_firmware_image, netboot_firmware_image)

  def Run(self):
    mini_omaha_url = 'http://%s:%d/update' % (self.options.mini_omaha_ip,
                                              self.options.mini_omaha_port)
    self.UpdateManifest(mini_omaha_url)
    self.UpdateInstallShim(mini_omaha_url)
    self.UpdateUbootNetboot(mini_omaha_url)
    self.UpdateDepthchargeNetboot(mini_omaha_url)
