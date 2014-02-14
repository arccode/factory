# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for creating factory bundle."""

import logging
import os
import re
import sys
import tempfile
import time
import yaml

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import board_cmd_arg, FactoryFlowCommand
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import factory
from cros.factory.tools.gsutil import GSUtil
from cros.factory.umpire.common import LoadBundleManifest
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class CreateBundleError(Exception):
  """Create bundle error."""


class CreateBundle(FactoryFlowCommand):
  """Creates factory bundle.

  The version arguments below can be one of:
  - from_manifest: Re-use the one in manifest (default).
  - stablest: Try to get the stablest build starting from stable -> beta ->
      dev -> canary.
  - <channel>/<version>: Try to get the given version from the given channel.
      For example:
        - beta: Use latest build from beta channel.
        - 4262.153.0: Search through channels just like stablest does and use
            the stablest channel that supports this version.
        - canary/4262: Use latest build from 4262 branch of canary channel.
        - stable/5467.0.0: Use version 5467.0.0 of stable channel.
  """
  args = [
      board_cmd_arg,
      CmdArg('--output-dir', help='the output directory'),
      CmdArg('--factory-version',
             help=('the version of factory zip to use; the factory toolkit'
                   'is extracted from the zip file (default: %(default)s)'),
             default='canary'),
      CmdArg('--test-version',
             help='the version of test image to use (default: %(default)s)',
             default='canary'),
      CmdArg('--release-version',
             help='the version of release image to use (default: %(default)s)',
             default='from_manifest'),
      CmdArg('--netboot-firmware-version',
             help=('the version of netboot firmware image to use '
                   '(default: %(default)s)'),
             default='from_manifest'),
      CmdArg('--netboot-kernel-version',
             help=('the version of netboot kernel image to use '
                   '(default: %(default)s)'),
             default='from_manifest'),
      CmdArg('--factory-shim-version',
             help=('the version of factory shim image to use '
                   '(default: %(default)s)'),
             default='from_manifest'),
      CmdArg('--no-use-toolkit', dest='use_toolkit',
             action='store_false', default=True,
             help='do not use factory toolkit in finalize bundle'),
      CmdArg('--mini-omaha-ip', default=None,
             help=('IP address of the mini omaha server; set this to None to '
                   'rely on DHCP server to provide the IP address '
                   '(default: %(default)s)')),
      CmdArg('--mini-omaha-port', type=int,
             help='Port of the mini omaha server (default: %(default)s)',
             default=8080),
  ]

  gsutil = None
  output_dir = None

  # The followings are set after factory zip is extracted.
  bundle_dir = None
  bundle_name = None

  VERSION_ARG_RE = {
      'from_manifest': re.compile(r'^from_manifest$'),
      'stablest': re.compile(r'^stablest$'),
      # The channel and/or the version/branch.
      'channel_and_version': re.compile(
          r'^(stable|beta|dev|canary)?/?(\d+(?:\.\d+){0,2})?$'),
  }

  # A dict of the file types we are using in this module to the associated
  # image types and their signed version (if applicable).
  FILETYPE_MAP = {
      # Factory zip; unsigned.
      'factory': (GSUtil.IMAGE_TYPES.factory, (None,)),
      # Factory shim; only look for signed one since the unsigned one is in
      # factory zip.
      'factory_shim': (GSUtil.IMAGE_TYPES.factory, ('.*',)),
      # Release image; look for signed one first and fall back to unsigned one.
      'release': (GSUtil.IMAGE_TYPES.recovery, ('.*', None)),
      # Test image; unsigned.
      'test': (GSUtil.IMAGE_TYPES.test, (None,)),
      # Netboot firmware; unsigned.
      'netboot_firmware': (GSUtil.IMAGE_TYPES.firmware, (None,)),
      # Netboot kernel; unsigned.
      'netboot_kernel': (GSUtil.IMAGE_TYPES.factory, (None,)),
  }

  def Init(self):
    self.gsutil = GSUtil(self.options.board.full_name)
    self.output_dir = (
        self.options.output_dir or tempfile.mkdtemp(prefix='create_bundle.'))
    self.bundle_name = time.strftime('%Y%m%d') + '_testing'

  def Run(self):
    self.FetchAndExtractFactoryZip()
    self.PrepareManifest()
    self.PrepareReadme()
    self.FinalizeBundle()

  def _GetImageURL(self, file_type, channel=None, version=None):
    """Gets the URL of the given file type from Google Storage.

    Args:
      file_type: The file type to get URL for.
      channel: The Google Storage channel to search URL from.
      version: The build version.

    Returns:
      The URL got from Google Storage.

    Raises:
      CreateBundleError if unable to find a matched image.
    """
    image_type, keys = self.FILETYPE_MAP[file_type]
    channels_to_search = (
        (channel,) if channel else ('stable', 'beta', 'dev', 'canary'))
    for channel in channels_to_search:
      for key in keys:
        try:
          gs_url = self.gsutil.GetLatestBuildPath(channel, branch=version)
          return self.gsutil.GetBinaryURI(gs_url, image_type, key=key)
        except Exception:
          # Try next key or channel.
          pass
    raise CreateBundleError(
        'Unable to find %s image matching: channel=%s, version=%s' %
        (file_type, channel, version))

  def _ParseImageVersionToURL(self, file_type, version_str, manifest=None):
    """Parses the version arg of the given file type and returns its GS URL.

    Args:
      file_type: The file type to parse.  Choices are: ('factory',
        'factory_shim', 'release', 'test', 'netboot_firmware',
        'netboot_kernel').
      version_str: The version argument string.
      manifest: A manifest dict.  Used for 'from_manifest'.

    Returns:
      The resulting URL.

    Raises:
      CreateBundleError if version arg is invalid or cannot find image URL in
      manifest (in case of 'from_manifest').
    """
    if not any(arg_re.match(version_str) for arg_re in
               self.VERSION_ARG_RE.itervalues()):
      raise CreateBundleError('Invalid version arg %r' % version_str)

    if self.VERSION_ARG_RE['from_manifest'].match(version_str):
      if not manifest:
        # No existing manifest provided; fall back to stablest.
        version_str = 'stablest'
      else:
        def GetSourceFromMatchedDict(list_of_dict, dict_to_match,
                                     extra_check=None):
          """Gets the 'source' field from a matched entry a list of dicts.

          Args:
            list_of_dict: The list of dicts to search for a match.
            dict_to_match: A dict of key of regular expressions.
            extra_check: An optional callable for doing an extra check on dict
              entry.
          """
          for d in list_of_dict:
            if all(re.match(v, d.get(k)) for (k, v) in
                   dict_to_match.iteritems()):
              if extra_check and not extra_check(d):
                continue
              return d['source']
          return None

        if file_type == 'factory_shim':
          url = GetSourceFromMatchedDict(
              manifest.get('add_files', {}),
              dict(install_into=r'factory_shim',
                   source=r'^.*factory.*\.bin$'))
        elif file_type == 'release':
          url = GetSourceFromMatchedDict(
              manifest.get('add_files', {}),
              dict(install_into=r'release',
                   source=r'^.*recovery.*\.bin$|^.*recovery.*\.tar\.xz$'))
        elif file_type == 'test':
          url = manifest.get('test_image_version')
        elif file_type == 'netboot_firmware':
          url = GetSourceFromMatchedDict(
              manifest.get('add_files', {}),
              dict(install_into=r'netboot_firmware',
                   source=r'^.*firmware.*\.tar\.bz2$'))
        elif file_type == 'netboot_kernel':
          url = GetSourceFromMatchedDict(
              manifest.get('add_files', {}),
              dict(install_into=r'\.',
                   source=r'^.*\.zip$'),
              extra_check=lambda file_spec: (
                  'factory_shim/netboot/vmlinux.uimg' in
                  file_spec.get('extract_files', [])))
        else:
          raise CreateBundleError(
              'Manifest does not have source for %s image' % file_type)

        if url:
          return url
        else:
          logging.info(
              ('Unable to find source URL for %s in manifest; '
               'fall back to stablest'), file_type)
          version_str = 'stablest'

    if self.VERSION_ARG_RE['stablest'].match(version_str):
      return self._GetImageURL(file_type)
    else:
      channel, version = self.VERSION_ARG_RE['channel_and_version'].match(
          version_str).groups()
      return self._GetImageURL(file_type, channel=channel, version=version)

  def FetchAndExtractFactoryZip(self):
    """Fetches factory zip from Google Storage and extracts it.

    The factory version provided by '--factory-version' is used here to get the
    zip file.  The bundle directory is renamed to 'YYYYMMDD_testing' and is used
    as the base testing bundle.

    Raises:
      CreateBundleError if output bundle directory exists.
    """
    factory_url = self._ParseImageVersionToURL('factory',
                                               self.options.factory_version)
    logging.info('Fetching and extracting %s', factory_url)
    factory_zip_path = self.gsutil.GSDownload(factory_url)
    temp_bundle_dir = os.path.join(self.output_dir, 'temp_factory_zip')
    file_utils.ExtractFile(factory_zip_path, temp_bundle_dir)

    # Rename bundle directory to the correct name.
    manifest = LoadBundleManifest(
        os.path.join(temp_bundle_dir, 'MANIFEST.yaml'))
    self.bundle_dir = os.path.join(self.output_dir, 'factory_bundle_%s_%s' % (
        manifest['board'], self.bundle_name))
    if os.path.exists(self.bundle_dir):
      raise CreateBundleError(
          'Target bundle directory %r exists' % self.bundle_dir)
    os.rename(temp_bundle_dir, self.bundle_dir)
    logging.info('Base bundle extracted at %s', self.bundle_dir)

  def PrepareManifest(self):
    """Generates a testing MANIFEST.yaml file for finalize_bundle.

    Backs up the original MANIFEST.yaml if one is found.

    Raises:
      CreateBundleError if cannot locate a valid netboot firmware from the input
      URL.
    """
    logging.info('Preparing MANIFEST.yaml')
    manifest = None
    template_manifest_path = os.path.join(
        factory.FACTORY_PATH, 'py', 'factory_flow', 'templates',
        'MANIFEST_template.yaml')
    manifest = LoadBundleManifest(template_manifest_path)

    manifest_in_zip = None
    output_manifest_path = os.path.join(self.bundle_dir, 'MANIFEST.yaml')
    if os.path.exists(output_manifest_path):
      manifest_in_zip = LoadBundleManifest(output_manifest_path)
      # Backup the original manifest file as we are going to create a new one.
      os.rename(output_manifest_path, output_manifest_path + '.original')

    manifest['board'] = self.options.board.full_name
    manifest['bundle_name'] = self.bundle_name

    # Add release image.
    release_url = self._ParseImageVersionToURL(
        'release', self.options.release_version, manifest=manifest_in_zip)
    file_spec = dict(install_into='release', source=release_url)
    if not release_url.endswith('.bin'):
      file_spec['extract_files'] = ['recovery_image.bin']
    manifest['add_files'].append(file_spec)

    # Add netboot firmware.
    netboot_firmware_url = self._ParseImageVersionToURL(
        'netboot_firmware', self.options.netboot_firmware_version,
        manifest=manifest_in_zip)
    # We need to see the content of the firmware tarball to determine what
    # firmware binary we are going to extract. The file names we are looking for
    # in the tarball are:
    #   - uboot: nv_image-<board>.bin
    #   - depthcharge: image.net.bin
    #
    # There is only one of the above binary in the tarball.
    netboot_firmware_tarball_cache = GSUtil.GSDownload(netboot_firmware_url)
    tarball_files = process_utils.CheckOutput(
        ['tar', '-tf', netboot_firmware_tarball_cache])
    if 'image.net.bin' in tarball_files:
      netboot_firmware = 'image.net.bin'
    elif 'nv_image-%s.bin' % self.options.board.short_name in tarball_files:
      netboot_firmware = 'nv_image-%s.bin' % self.options.board.short_name
    else:
      raise CreateBundleError(
          'Cannot locate a valid netboot firmware in %r' % netboot_firmware_url)
    manifest['add_files'].append(
        dict(install_into='netboot_firmware',
             extract_files=['ec.bin', netboot_firmware],
             source=netboot_firmware_url))
    # Put a copy in factory/board. This is required by the reimage factory test.
    manifest['add_files_to_image'].append(
        dict(install_into='factory/board',
             source='netboot_firmware/%s' % netboot_firmware))

    # Add netboot kernel.
    netboot_kernel_url = self._ParseImageVersionToURL(
        'netboot_kernel', self.options.netboot_kernel_version,
        manifest=manifest_in_zip)
    manifest['add_files'].append(
        dict(install_into='.',
             extract_files=['factory_shim/netboot/vmlinux.uimg'],
             source=netboot_kernel_url))

    # Add factory install shim.
    try:
      factory_shim_url = self._ParseImageVersionToURL(
          'factory_shim', self.options.factory_shim_version,
          manifest=manifest_in_zip)
      if factory_shim_url.endswith('.bin'):
        # Found a signed factory install shim; remove the unsigned one.
        manifest['delete_files'].append('factory_shim/factory_install_shim.bin')
      manifest['add_files'].append(
          dict(install_into='factory_shim',
               source=factory_shim_url))
    except CreateBundleError:
      # Signed factory install shim only exist on factory branch; no sweat here.
      logging.info(
          ('Cannot locate a signed factory shim for %s on Google Storage; '
           'if you want to test signed factory shim, specify --factory-version '
           'to %s factory branch to locate it'),
          self.options.board.full_name, self.options.board.full_name)

    # Add test image.
    test_url = self._ParseImageVersionToURL(
        'test', self.options.test_version, manifest=manifest_in_zip)
    manifest['test_image_version'] = test_url

    # Remove complete script to unblock the DUT after installation is done.
    manifest['complete_script'] = None

    # Update mini omaha URL.
    if self.options.mini_omaha_ip:
      manifest['mini_omaha_url'] = 'http://%s:%d/update' %  (
          self.options.mini_omaha_ip, self.options.mini_omaha_port)

    manifest['use_factory_toolkit'] = self.options.use_toolkit

    with open(output_manifest_path, 'w') as f:
      f.write(yaml.dump(manifest, default_flow_style=False))

  def PrepareReadme(self):
    """Generates a testing README file for finalize_bundle.

    Backs up the original README in the bundle if one is found.
    """
    input_readme_path = os.path.join(
        factory.FACTORY_PATH, 'py', 'factory_flow', 'templates',
        'README_template')

    readme = None
    with open(input_readme_path) as f:
      readme = f.read()
    readme += '\n'.join([
        '',
        '%s changes:' % self.bundle_name,
        '  Testing bundle generated with the following command: ',
        '    %s' % ' '.join(sys.argv),
        ''])

    output_readme_path = os.path.join(
        self.bundle_dir, 'README')
    if os.path.exists(output_readme_path):
      # Backup the original README file as we are going to create a new one.
      os.rename(output_readme_path, output_readme_path + '.original')
    with open(output_readme_path, 'w') as f:
      f.write(readme)

  def FinalizeBundle(self):
    """Calls finalize_bundle to create the testing factory bundle."""
    logging.info('Finalizing factory bundle %s', self.bundle_dir)
    finalize_bundle_tool = os.path.join(factory.FACTORY_PATH, 'bin',
                                        'finalize_bundle')
    process_utils.Spawn([finalize_bundle_tool, '--no-check-files',
                         '--no-archive', self.bundle_dir],
                        log=True, check_call=True)
