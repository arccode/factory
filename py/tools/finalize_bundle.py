#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tools to finalize a factory bundle."""

from __future__ import print_function

import argparse
import contextlib
import errno
import glob
import logging
import os
import re
import shutil
import sys
import textwrap
import time
import urlparse
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.tools import build_board
from cros.factory.tools import get_version
from cros.factory.tools import gsutil
from cros.factory.utils.file_utils import TryUnlink, ExtractFile, WriteWithSudo
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountPartition
from cros.factory.utils.type_utils import CheckDictKeys


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

REQUIRED_GSUTIL_VERSION = [3, 32]  # 3.32

DELETION_MARKER_SUFFIX = '_DELETED'

# Default firmware labels to get version and update in README file.
# To override it, assign 'has_firmware' in MANIFEST.yaml.
# Examples:
# has_firmware: [BIOS]
# has_firmware: [EC, BIOS]
# has_firmware: [EC, BIOS, PD]
DEFAULT_FIRMWARES = ['BIOS', 'EC']

FIRMWARE_UPDATER_NAME = 'chromeos-firmwareupdate'
FIRMWARE_UPDATER_PATH = os.path.join('usr', 'sbin', FIRMWARE_UPDATER_NAME)

# Special string to use a local file instead of downloading one.
LOCAL = 'local'


# Legacy: resources may live in different places due to historical reason. To
# maintain backward compatibility, we have to search for a set of directories.
# TODO(crbug.com/706756): once we completely remove the old directories, we can
#                         simple make this a string instead of a list of
#                         strings.
TEST_IMAGE_SEARCH_DIRS = ['test_image', 'factory_test']
RELEASE_IMAGE_SEARCH_DIRS = ['release_image', 'release']
TOOLKIT_SEARCH_DIRS = ['toolkit', 'factory_toolkit']

# When version is fixed, we'll try to find the resource in the following order.
RESOURCE_CHANNELS = ['stable', 'beta', 'dev', 'canary']


def _GetReleaseVersion(mount_point):
  """Returns the release version of an image mounted at mount_point."""
  result = get_version.GetReleaseVersion(mount_point)
  if not result:
    sys.exit('Unable to read lsb-release from %s' % mount_point)
  return result


def _GetFirmwareVersions(updater, expected_firmwares):
  """Returns the firmware versions in an updater.

  Args:
    updater: Path to a firmware updater.
    expected_firmwares: a list containing the expected firmware labels to
        get version, ex: ['BIOS', EC'].

  Returns:
    {'BIOS': bios_version, 'EC': ec_version, 'PD': pd_version}.
    If the firmware is not found, the version will be None.
  """
  versions = get_version.GetFirmwareVersionsWithLabel(updater)

  for label in expected_firmwares:
    if versions.get(label) is None:
      sys.exit('Unable to read %r version from %s' % (label,
                                                      FIRMWARE_UPDATER_NAME))

  return versions


USAGE = """
Finalizes a factory bundle.  This script checks to make sure that the
bundle is valid, outputs version information into the README file, and
tars up the bundle.

The input is a MANIFEST.yaml file like the following:

  board: link
  bundle_name: 20121115_pvt

  # Specify the version of test image directly.
  test_image: 9876.0.0

  # Specify that a local release image should be used.
  release_image: local

  # Specify the version of factory toolkit directly.
  toolkit: 9678.12.0

  # Files to download and add to the bundle.
  add_files:
  - install_into: release
    source: "gs://.../chromeos_recovery_image.bin"
  - install_into: firmware_images
    extract_files: [ec.bin, image.bin]
    source: 'gs://.../ChromeOS-firmware-...tar.bz2'
"""


class FinalizeBundle(object):
  """Finalizes a factory bundle (see USAGE).

  Properties:
    args: Command-line arguments from argparse.
    bundle_dir: Path to the bundle directory.
    bundle_name: Name of the bundle (e.g., 20121115_proto).
    build_board: The BuildBoard object for the board.
    board: Board name (e.g., link).
    simple_board: For board name like "base_variant", simple_board is "variant".
      simple_board == board if board is not a variant board.
      This name is used in firmware and hwid.
    manifest: Parsed YAML manifest.
    readme_path: Path to the README file within the bundle.
    install_shim_version: Build of the install shim.
    new_factory_par: Path to a replacement factory.par.
    test_image_source: Source (LOCAL or a version) of the test image.
    test_image_path: Path to the test image.
    test_image_version: Version of the test image.
    release_image_source : Source (LOCAL or a version) of the release image.
    release_image_path: Path to the release image.
    release_image_version: Version of the release image.
    toolkit_source: Source (LOCAL or a version) of the factory toolkit.
    toolkit_path: Path to the factory toolkit.
    toolkit_version: Version of the factory toolkit.
    gsutil: A GSUtil object.
  """
  args = None
  bundle_dir = None
  bundle_name = None
  build_board = None
  board = None
  simple_board = None
  manifest = None
  readme_path = None
  install_shim_version = None
  new_factory_par = None
  test_image_source = None
  test_image_path = None
  test_image_version = None
  release_image_source = None
  release_image_path = None
  release_image_version = None
  toolkit_source = None
  toolkit_path = None
  toolkit_version = None
  gsutil = None
  has_firmware = DEFAULT_FIRMWARES

  def Main(self):
    self.ParseArgs()
    self.LoadManifest()
    self.LocateResources()
    self.DownloadResources()
    self.AddDefaultCompleteScript()
    self.CheckAndAddDummyHWID()
    self.AddFirmwareUpdaterAndImages()
    self.GetAndSetResourceVersions()
    self.PrepareNetboot()
    self.UpdateInstallShim()
    self.FixFactoryPar()
    self.CreateStartDownloadServerSymlink()
    self.RemoveUnnecessaryFiles()
    self.UpdateReadme()
    self.Archive()

  def ParseArgs(self):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=USAGE)

    parser.add_argument(
        '--no-download', dest='download', action='store_false',
        help="Don't download files from Google Storage (for testing only)")
    parser.add_argument(
        '--no-archive', dest='archive', action='store_false',
        help="Don't make a tarball (for testing only)")

    parser.add_argument('manifest', metavar='MANIFEST',
                        help=(
                            'Path to the manifest file or the directory '
                            'containing MANIFEST.yaml'))
    parser.add_argument('dir', metavar='DIR', nargs='?',
                        default=None, help='Working directory')

    self.args = parser.parse_args()

  def LoadManifest(self):
    if os.path.isdir(self.args.manifest):
      manifest_path = os.path.join(self.args.manifest, 'MANIFEST.yaml')
    else:
      manifest_path = self.args.manifest
    self.manifest = yaml.load(file_utils.ReadFile(manifest_path))
    CheckDictKeys(self.manifest,
                  ['board', 'bundle_name', 'add_files', 'server_url',
                   'toolkit', 'test_image', 'release_image', 'firmware', 'hwid',
                   'has_firmware'])

    self.build_board = build_board.BuildBoard(self.manifest['board'])
    self.board = self.build_board.full_name
    self.simple_board = self.build_board.short_name
    self.gsutil = gsutil.GSUtil(self.board)

    self.bundle_name = self.manifest['bundle_name']
    if not re.match(r'\d{8}_', self.bundle_name):
      sys.exit("The bundle_name (currently %r) should be today's date, "
               'plus an underscore, plus a description of the build, e.g.: %r' %
               (self.bundle_name, time.strftime('%Y%m%d_proto')))

    work_dir = self.args.dir or os.path.dirname(os.path.realpath(manifest_path))

    # If the basename of the working directory is equal to the expected name, we
    # believe that the user intentionally wants to make the bundle in the
    # working directory (this is also needed if any of the resource is assigned
    # as local). Otherwise, we'll create a directory with expected name under
    # the working directory.
    expected_dir_name = 'factory_bundle_%s_%s' % (self.board, self.bundle_name)
    logging.info('Expected bundle directory name is %r', expected_dir_name)
    if expected_dir_name == os.path.basename(work_dir):
      self.bundle_dir = work_dir
      logging.info('The working directory name matches the expected bundle '
                   'directory name, will finalized bundle directly in the '
                   'working directory %r', self.bundle_dir)
    else:
      self.bundle_dir = os.path.join(work_dir, expected_dir_name)
      logging.info('The working directory name does not match the expected '
                   'bundle directory name, will create a new directoy and '
                   'finalize bundle in %r', self.bundle_dir)
    self.bundle_dir = os.path.realpath(self.bundle_dir)
    file_utils.TryMakeDirs(self.bundle_dir)

    self.test_image_source = self.manifest.get('test_image')
    self.release_image_source = self.manifest.get('release_image')
    self.toolkit_source = self.manifest.get('toolkit')

    self.readme_path = os.path.join(self.bundle_dir, 'README')
    self.has_firmware = self.manifest.get('has_firmware', DEFAULT_FIRMWARES)

  def _GetImageVersion(self, image_path):
    """Returns version of the image."""
    with MountPartition(image_path, 3) as m:
      return _GetReleaseVersion(m)

  def _MatchImageVersion(self, image_path, requested_version):
    """Returns True if an image matches the requested version, False
    otherwise."""
    logging.info('Checking whether the version of image %r is %r',
                 image_path, requested_version)
    image_version = self._GetImageVersion(image_path)
    logging.info('Version of image %r is %r', image_path, image_version)
    return image_version == requested_version

  def _LocateOneResource(self, resource_name, resource_source, search_dirs,
                         version_checker):
    """Locates a resource under all search directories.

    This function tries to locate a local resource under all search_dirs
    (relative to self.bundle_dir). If multiple resources were found, an
    exception will be raised. If resource_source is LOCAL but no resource was
    found, an exception will also be raised. See details below.

    Resource source can be LOCAL or non-LOCAL; found entries can be 0, 1, or
    multiple, and here's how we should react to each case:

    found   LOCAL    non-LOCAL
    ------------------------------------------------------------
       =0   reject   accept (will download later)
       =1   accept   accept if version matches, reject otherwise
       >1   reject   reject

    Args:
      resource_name: name of the resource, such as 'test image' or
          'factory toolkit'.
      resource_source: source of the resource, LOCAL or a version string.
      search_dirs: a list of directories under self.bundle_dir to search. Every
          element in this list will be joined to self.bundle_dir first.
      version_checker: a callable that with signature
          (resource_path, requested_version) that returns True if the resource
          matches the requested_version, False otherwise.

    Returns:
      Path to the resource (if only one is found and its version matches).
    """
    abs_search_dirs = [os.path.join(self.bundle_dir, d) for d in search_dirs]

    # TODO(crbug.com/706756): once the directory structure has been fixed, we
    #                         can just build up the path instead of searching
    #                         through all search_dirs.
    logging.info('Searching %s in %r', resource_name, search_dirs)
    found_entries = FinalizeBundle._ListAllFilesIn(abs_search_dirs)

    len_found_entries = len(found_entries)
    resource_path = None
    is_local = resource_source == LOCAL

    if len_found_entries == 1:
      resource_path = found_entries[0]
      logging.info(
          'A local copy of %s is found at %r', resource_name, resource_path)
      if not is_local and not version_checker(resource_path, resource_source):
        raise Exception(
            'Requested %s version is %r but found a local one with different '
            'version at %r' % (resource_name, resource_source, resource_path))
    elif len_found_entries > 1:
      raise Exception(
          'There should be only one %s in %r but found multiple: %r' % (
              resource_name, search_dirs, found_entries))
    else:
      assert len_found_entries == 0
      if is_local:
        raise Exception(
            '%s source is specified as %r but no one found under %r' % (
                resource_name.capitalize(), LOCAL, abs_search_dirs))
      if not self.args.download:
        raise Exception(
            'Need %s but no files found under %r' % (
                resource_name.capitalize(), abs_search_dirs))
      # Will be downloaded later.

    return resource_path

  def LocateResources(self):
    """Locates test image, release image, and factory toolkit.

    This function tries to locate test image, release image, and factory toolkit
    in self.bundle_dir, and sets the following attributes respectively:
    - self.test_image_path
    - self.releases_image_path
    - self.toolkit_path

    If a resource is found, the corresponding attribute is set to its path; if
    it's not found, the attribute is set to None (and we'll raise an error if
    the source of the resource is set to LOCAL or if self.args.download is set
    to False in this case).
    """
    self.test_image_path = self._LocateOneResource(
        'test image', self.test_image_source, TEST_IMAGE_SEARCH_DIRS,
        self._MatchImageVersion)
    self.release_image_path = self._LocateOneResource(
        'release image', self.release_image_source, RELEASE_IMAGE_SEARCH_DIRS,
        self._MatchImageVersion)

    # TODO(crbug.com/707155): see #c1. Unlike images, we don't handle non-local
    #     case even if a local toolkit is found. It's not possible to be certain
    #     that the version of the local toolkit matches the requested one
    #     because we should not only consider the toolkit but also other
    #     resources. We have to always download. So the version_checker should
    #     always return True.
    self.toolkit_path = self._LocateOneResource(
        'factory toolkit', self.toolkit_source, TOOLKIT_SEARCH_DIRS,
        lambda unused_path, unused_version: True)

  def _CheckGSUtilVersion(self):
    # Check for gsutil >= 3.32.
    version = self.gsutil.GetVersion()
    # Remove 'pre...' string at the end, if any
    version = re.sub('pre.*', '', version)
    version_split = [int(x) for x in version.split('.')]
    if version_split < REQUIRED_GSUTIL_VERSION:
      sys.exit(
          'gsutil version >=%s is required; you seem to have %s.\n'
          'Please download and install gsutil ('
          'https://developers.google.com/storage/docs/gsutil_install), and '
          'make sure this is in your PATH before the system gsutil.' % (
              '.'.join(str(x) for x in REQUIRED_GSUTIL_VERSION), version))

  def DownloadResources(self):
    """Downloads test image, release image, factory toolkit if needed."""

    need_test_image = (self.test_image_source != LOCAL and
                       self.test_image_path is None)
    need_release_image = (self.release_image_source != LOCAL and
                          self.release_image_path is None)

    # TODO(crbug.com/707155): see #c1. We have to always download the factory
    #                         toolkit unless the "toolkit" source in config
    #                         refers to only the toolkit version instead of
    #                         factory.zip.
    need_toolkit = (self.toolkit_source != LOCAL)

    if (not 'add_files' in self.manifest and
        not need_test_image and not need_release_image and not need_toolkit):
      return

    # Make sure gsutil is up to date; older versions are pretty broken.
    self._CheckGSUtilVersion()

    if self.args.download:
      if need_test_image:
        self.test_image_path = self._DownloadTestImage(
            self.test_image_source,
            os.path.join(self.bundle_dir, TEST_IMAGE_SEARCH_DIRS[0]))
      if not os.path.exists(self.test_image_path):
        raise Exception('No test image at %s' % self.test_image_path)

      if need_release_image:
        self.release_image_path = self._DownloadReleaseImage(
            self.release_image_source,
            os.path.join(self.bundle_dir, RELEASE_IMAGE_SEARCH_DIRS[0]))
      if not os.path.exists(self.release_image_path):
        raise Exception('No release image at %s' % self.release_image_path)

      if need_toolkit:
        self.toolkit_path = self._DownloadFactoryToolkit(self.toolkit_source,
                                                         self.bundle_dir)

    # TODO(b/36702884): remove this section once finalize_bundle supports
    #                   grabbing firmware from different sources
    # TODO(littlecvr): merge LocateResources(), DownloadResources(), and
    #                  GetAndSetResourceVersions(). If this section is removed,
    #                  DownloadResources() becomes simple enough to be merged.
    #                  One thing to note is that we should make finalize_bundle
    #                  workable without gsutil if all resources come from LOCAL.
    #                  Therefore, when merging these function, make sure we
    #                  don't call self._CheckGSUtilVersion() if not necessary.
    for f in self.manifest.get('add_files', []):
      CheckDictKeys(f, ['install_into', 'source', 'extract_files'])
      dest_dir = os.path.join(self.bundle_dir, f['install_into'])
      file_utils.TryMakeDirs(dest_dir)

      source = f['source'].replace('${BOARD}', self.simple_board.upper())

      if self.args.download:
        cached_file = self._DownloadResource([source])

      if f.get('extract_files'):
        install_into = os.path.join(self.bundle_dir, f['install_into'])
        if self.args.download:
          ExtractFile(cached_file, install_into,
                      only_extracts=f['extract_files'])
      else:
        dest_path = os.path.join(dest_dir, os.path.basename(source))
        if self.args.download:
          shutil.copyfile(cached_file, dest_path)

  def GetAndSetResourceVersions(self):
    """Gets and sets versions of test, release image, and factory toolkit."""
    self.test_image_version = self._GetImageVersion(self.test_image_path)
    logging.info('Test image version: %s', self.test_image_version)

    self.release_image_version = self._GetImageVersion(self.release_image_path)
    logging.info('Release image version: %s', self.release_image_version)

    output = Spawn([self.toolkit_path, '--info'], check_output=True).stdout_data
    match = re.match(r'^Identification: .+ Factory Toolkit (.+)$', output, re.M)
    assert match, 'Unable to parse toolkit info: %r' % output
    self.toolkit_version = match.group(1)  # May be None if locally built
    logging.info('Toolkit version: %s', self.toolkit_version)

  def AddDefaultCompleteScript(self):
    """Adds default complete script if not set."""
    complete_dir = os.path.join(self.bundle_dir, 'complete')
    file_utils.TryMakeDirs(complete_dir)
    num_complete_scripts = len(os.listdir(complete_dir))

    if num_complete_scripts == 1:
      # Complete script already provided.
      return
    elif num_complete_scripts > 1:
      raise Exception('Not having exactly one file under %s.' % complete_dir)

    default_complete_script = os.path.join(
        self.bundle_dir, 'setup', 'complete_script_sample.sh')
    shutil.copy(default_complete_script, complete_dir)

  def CheckAndAddDummyHWID(self):
    """Check number of files in hwid/, and add dummy HWID bundle if there is no
    file and given 'hwid: none'."""
    dummy_name = 'hwid_v3_bundle_DUMMY.sh'
    hwid_dir = os.path.join(self.bundle_dir, 'hwid')
    hwid_lst = os.listdir(hwid_dir)
    hwid_num = len(hwid_lst)
    if hwid_num > 1:
      raise Exception('There are multiple files under %s.' % hwid_dir)
    elif self.manifest.get('hwid') == 'none':
      if hwid_num == 1:
        # We should check if it is a real HWID bundle for local toolkit.
        # Or users might always use 'hwid: none'.
        if self.toolkit_source == LOCAL and hwid_lst[0] != dummy_name:
          raise Exception(
              'hwid is set to none but found a non-dummy HWID bundle.')
      else:
        file_utils.WriteFile(
            os.path.join(hwid_dir, dummy_name),
            '\n'.join([
                '#!/bin/sh',
                'exit',
                'checksum: DUMMY',
                '']))
    else:  # hwid: real
      if hwid_num == 0:
        raise Exception(
            "Please add 'hwid: none' in manifest file explicitly if you don't "
            "have a real HWID bundle now.")
      elif hwid_lst[0] == dummy_name:
        raise Exception(
            'hwid is not set to none but found a dummy HWID bundle.')

  def AddFirmwareUpdaterAndImages(self):
    """Add firmware updater into bundle directory, and extract firmware images
    into firmware_images/."""

    firmware_src = self.manifest.get('firmware', 'release_image')
    firmware_dir = os.path.join(self.bundle_dir, 'firmware')
    file_utils.TryMakeDirs(firmware_dir)
    if firmware_src == 'release_image':
      with MountPartition(self.release_image_path, 3) as f:
        shutil.copy(os.path.join(f, FIRMWARE_UPDATER_PATH), firmware_dir)
    elif firmware_src != LOCAL:
      raise Exception('firmware must be either "release_image" or "%s".' %
                      LOCAL)
    updaters = os.listdir(firmware_dir)
    if len(updaters) != 1:
      raise Exception('Not having exactly one file under %s.' % firmware_dir)

    firmware_images_dir = os.path.join(self.bundle_dir, 'firmware_images')
    file_utils.TryMakeDirs(firmware_images_dir)
    Spawn(['sh', os.path.join(firmware_dir, updaters[0]),
           '--sb_extract', firmware_images_dir], log=True, check_call=True)
    for filename in os.listdir(firmware_images_dir):
      if not filename.endswith('.bin'):
        file_utils.TryUnlink(os.path.join(firmware_images_dir, filename))

  def PrepareNetboot(self):
    """Prepares netboot resource for TFTP setup."""
    # TODO(hungte) Change factory_shim/netboot/ to be netboot/ in factory.zip.
    orig_netboot_dir = os.path.join(self.bundle_dir, 'factory_shim', 'netboot')
    netboot_dir = os.path.join(self.bundle_dir, 'netboot')
    if os.path.exists(orig_netboot_dir) and not os.path.exists(netboot_dir):
      shutil.move(orig_netboot_dir, netboot_dir)

    if not os.path.exists(netboot_dir):
      logging.info('No netboot resources.')
      return

    # Try same convention that sys-boot/chromeos-bootimage is doing:
    # bootfile=${PORTAGE_USERNAME}/${BOARD_USE}/vmlinuz
    # argfile=${PORTAGE_USERNAME}/${BOARD_USE}/cmdline
    files_dir = os.path.join('chrome-bot', self.board)
    target_bootfile = os.path.join(files_dir, 'vmlinuz')
    target_argsfile = os.path.join(files_dir, 'cmdline')
    netboot_firmware_settings = os.path.join(
        self.bundle_dir, 'setup', 'netboot_firmware_settings.py')

    server_url = self.manifest.get('server_url')
    tftp_server_ip = (urlparse.urlparse(server_url).hostname if server_url else
                      '')

    netboot_firmware_image = os.path.join(netboot_dir, 'image.net.bin')
    if os.path.exists(netboot_firmware_image):
      new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
      args = ['--argsfile', target_argsfile,
              '--bootfile', target_bootfile,
              '--input', netboot_firmware_image,
              '--output', new_netboot_firmware_image]
      if server_url:
        args += ['--omahaserver=%s' % server_url,
                 '--tftpserverip=%s' % tftp_server_ip]
      Spawn([netboot_firmware_settings] + args, check_call=True, log=True)
      shutil.move(new_netboot_firmware_image, netboot_firmware_image)

    tftp_root = os.path.join(self.bundle_dir, 'netboot', 'tftp')
    tftp_board_dir = os.path.join(tftp_root, files_dir)
    file_utils.TryMakeDirs(tftp_board_dir)

    # omaha_conf is fetched by factory_installer explicitly.
    if server_url:
      omaha_conf = os.path.join(tftp_root, 'omahaserver_%s.conf' % self.board)
      file_utils.WriteFile(omaha_conf, server_url)

    file_utils.WriteFile(os.path.join(tftp_root, '..', 'dnsmasq.conf'),
                         textwrap.dedent('''\
          # This is a sample config file to be invoked by `dnsmasq -d -C FILE`.
          interface=eth2
          tftp-root=/var/tftp
          enable-tftp
          dhcp-leasefile=/tmp/dnsmasq.leases
          dhcp-range=192.168.200.50,192.168.200.150,12h
          port=0
          '''))

    bootfile_path = os.path.join(netboot_dir, 'vmlinuz')
    if os.path.exists(bootfile_path):
      shutil.move(bootfile_path, os.path.join(tftp_board_dir, 'vmlinuz'))
    tftpserverip_config = (
        ('tftpserverip=%s' % tftp_server_ip) if tftp_server_ip else '')
    file_utils.WriteFile(
        os.path.join(tftp_board_dir, 'cmdline.sample'),
        'lsm.module_locking=0 cros_netboot_ramfs cros_factory_install '
        'cros_secure cros_netboot earlyprintk cros_debug loglevel=7 '
        '%s console=ttyS2,115200n8' % tftpserverip_config)

  def UpdateInstallShim(self):
    server_url = self.manifest.get('server_url')

    if not server_url:
      return

    def PatchLSBFactory(mount):
      """Patches lsb-factory in an image.

      Returns:
        True if there were any changes.
      """
      lsb_factory_path = os.path.join(
          mount, 'dev_image', 'etc', 'lsb-factory')
      logging.info('Patching lsb-factory in %s', lsb_factory_path)
      orig_lsb_factory = open(lsb_factory_path).read()
      lsb_factory = orig_lsb_factory

      if server_url:
        lsb_factory, number_of_subs = re.subn(
            r'(?m)^(CHROMEOS_(AU|DEV)SERVER=).+$', r'\1' + server_url,
            lsb_factory)
        if number_of_subs != 2:
          sys.exit('Unable to set mini-Omaha server in %s' % lsb_factory_path)

      if lsb_factory == orig_lsb_factory:
        return False  # No changes
      WriteWithSudo(lsb_factory_path, lsb_factory)
      return True

    def PatchInstallShim(shim):
      """Patches lsb-factory and updates self.install_shim_version."""
      def GetSigningKey(shim):
        """Derives signing key from factory install shim's file name."""
        if shim.endswith('factory_install_shim.bin'):
          return 'unsigned'
        key_match = re.search(r'channel_([\w\-]+)\.bin$', shim)
        if key_match:
          return key_match.group(1)
        else:
          # Error deriving signing key
          return 'undefined'

      with MountPartition(shim, 1, rw=True) as mount:
        PatchLSBFactory(mount)

      with MountPartition(shim, 3) as mount:
        self.install_shim_version = '%s (%s)' % (_GetReleaseVersion(mount),
                                                 GetSigningKey(shim))

    # Patch in the install shim, if present.
    has_install_shim = False
    unsigned_shim = os.path.join(self.bundle_dir, 'factory_shim',
                                 'factory_install_shim.bin')
    if os.path.isfile(unsigned_shim):
      PatchInstallShim(unsigned_shim)
      has_install_shim = True

    signed_shims = glob.glob(os.path.join(self.bundle_dir, 'factory_shim',
                                          'chromeos_*_factory*.bin'))
    if has_install_shim and signed_shims:
      sys.exit('Both unsigned and signed install shim exists. '
               'Please remove unsigned one')
    if len(signed_shims) > 1:
      sys.exit('Expected to find 1 signed factory shim but found %d: %r' % (
          len(signed_shims), signed_shims))
    elif len(signed_shims) == 1:
      PatchInstallShim(signed_shims[0])
      has_install_shim = True

    if not has_install_shim:
      logging.warning('There is no install shim in the bundle.')

  def CreateStartDownloadServerSymlink(self):
    """Create a symlink to start_download_server.sh in bundle directory."""
    script_name = 'start_download_server.sh'
    target_path = os.path.join(self.bundle_dir, 'setup', script_name)
    if not os.path.exists(target_path):
      logging.info('%s not found, symlink creation skipped.', target_path)
      return
    file_utils.SymlinkRelative(target_path,
                               os.path.join(self.bundle_dir, script_name),
                               force=True)
    file_utils.WriteFile(
        os.path.join(self.bundle_dir, 'setup', '.default_board'),
        '%s\n' % self.board)

  def FixFactoryPar(self):
    """Fix symlinks to factory.par, and replace factory.par if necessary.

    (Certain files may have been turned into real files by the buildbots.)
    """
    factory_par_path = os.path.join(self.bundle_dir, 'shopfloor', 'factory.par')
    factory_par_data = file_utils.ReadFile(factory_par_path)

    # Look for files that are identical copies of factory.par.
    for root, _, files in os.walk(self.bundle_dir):
      for f in files:
        path = os.path.join(root, f)
        if path == factory_par_path:
          # Don't replace it with itself!
          continue
        if (os.path.islink(path) or
            os.path.getsize(path) != len(factory_par_data)):
          # It's not a real file, or not the right size.  Skip.
          continue
        with open(path) as fobj:
          data = fobj.read()
        if data != factory_par_data:
          # Data isn't the same.  Skip.
          continue

        # Replace the file with a symlink.
        logging.info('Replacing %s with a symlink', path)
        os.unlink(path)
        os.symlink(os.path.relpath(factory_par_path, os.path.dirname(path)),
                   path)

    if self.new_factory_par:
      logging.info('Copying %s to %s', self.new_factory_par, factory_par_path)
      shutil.copy2(self.new_factory_par, factory_par_path)

  def RemoveUnnecessaryFiles(self):
    """Removes vim backup files, pyc files, and empty directories."""
    logging.info('Removing unnecessary files')
    for root, dirs, files in os.walk(self.bundle_dir):
      for f in files:  # Remove backup files and compiled Python files.
        if f.endswith('~') or f.endswith('.pyc'):
          path = os.path.join(root, f)
          os.unlink(path)
          logging.info('Removed file %r', path)
      for d in dirs:  # Remove any empty directories
        try:
          path = os.path.join(root, d)
          os.rmdir(path)
          logging.info('Removed empty directory %r', path)
        except OSError as e:
          if e.errno != errno.ENOTEMPTY:
            raise

  def UpdateReadme(self):
    # Grok the README file; we'll be modifying it.
    readme_sections = re.findall(
        # Section header
        r'(\*\*\*\n\*\n\* (.+?)\n\*\n\*\*\*\n)'
        # Anything up to (but not including) the next section header
        r'((?:(?!\*\*\*).)+)', file_utils.ReadFile(self.readme_path), re.DOTALL)
    # This results in a list of tuples (a, b, c), where a is the whole
    # section header string; b is the name of the section; and c is the
    # contents of the section.  Turn each tuple into a list; we'll be
    # modifying some of them.
    readme_sections = [list(x) for x in readme_sections]

    readme_section_index = {}  # Map of section name to index
    for i, s in enumerate(readme_sections):
      readme_section_index[s[1]] = i
    for k in ['VITAL INFORMATION', 'CHANGES']:
      if k not in readme_section_index:
        sys.exit('README is missing %s section' % k)

    # Make sure that the CHANGES section contains this version.
    expected_str = '%s changes:' % self.bundle_name
    if expected_str not in readme_sections[readme_section_index['CHANGES']][2]:
      logging.warning('The string %r was not found in the CHANGES section. '
                      'Please add a section for it (if this is the first '
                      'version, just say "initial release").', expected_str)

    def _ExtractFirmwareVersions(updater_file, updater_name):
      firmware_versions = _GetFirmwareVersions(updater_file, self.has_firmware)
      return [('%s %s' % (updater_name, firmware_type), version)
              for firmware_type, version in firmware_versions.iteritems()
              if version is not None]

    # Get some vital information
    vitals = [
        ('Board', self.board),
        ('Bundle', '%s (created by %s, %s)' % (
            self.bundle_name, os.environ['USER'],
            time.strftime('%a %Y-%m-%d %H:%M:%S %z')))]
    if self.toolkit_version:
      vitals.append(('Factory toolkit', self.toolkit_version))

    if self.test_image_source == LOCAL:
      with MountPartition(self.test_image_path, 3) as f:
        vitals.append(('Test image', '%s (local)' % _GetReleaseVersion(f)))
    elif self.test_image_source:
      vitals.append(('Test image', self.test_image_source))

    with MountPartition(self.test_image_path, 1) as f:
      stat = os.statvfs(f)
      stateful_free_bytes = stat.f_bfree * stat.f_bsize
      stateful_total_bytes = stat.f_blocks * stat.f_bsize
      vitals.append((
          'Stateful partition size',
          '%d MiB (%d MiB free = %d%% free)' % (
              stateful_total_bytes / 1024 / 1024,
              stateful_free_bytes / 1024 / 1024,
              int(stateful_free_bytes * 100.0 / stateful_total_bytes))))
      vitals.append((
          'Stateful partition inodes',
          '%d nodes (%d free)' % (stat.f_files, stat.f_ffree)))
    if self.install_shim_version:
      vitals.append(('Factory install shim', self.install_shim_version))
    with MountPartition(self.release_image_path, 3) as f:
      vitals.append(('Release (FSI)', _GetReleaseVersion(f)))
      vitals.extend(_ExtractFirmwareVersions(
          os.path.join(f, FIRMWARE_UPDATER_PATH), 'Release (FSI)'))

    # If we have any firmware in the tree, add them to the vitals.
    for root, unused_dirs, files in os.walk(self.bundle_dir):
      for f in files:
        path = os.path.join(root, f)
        relpath = os.path.relpath(path, self.bundle_dir)
        if f == FIRMWARE_UPDATER_NAME:
          vitals.extend(_ExtractFirmwareVersions(path, relpath))
        elif f in ['ec.bin', 'bios.bin', 'image.bin', 'image.net.bin']:
          version = get_version.GetFirmwareBinaryVersion(path)
          if not version:
            sys.exit('Unable to find firmware version in %s' % path)
          vitals.append((relpath, version))

    vital_lines = []
    max_key_length = max(len(k) for k, v in vitals)
    for k, v in vitals:
      vital_lines.append('%s:%s %s' % (k, ' ' * (max_key_length - len(k)), v))
    vital_contents = '\n'.join(vital_lines)
    readme_sections[readme_section_index['VITAL INFORMATION']][2] = (
        vital_contents + '\n\n')

    with open(self.readme_path, 'w') as f:
      for header, _, contents in readme_sections:
        f.write(header)
        f.write(contents)
    logging.info('\n\nUpdated %s; vital information:\n%s\n',
                 self.readme_path, vital_contents)

  def Archive(self):
    if self.args.archive:
      # Done! tar it up, and encourage the poor shmuck who has to build
      # the bundle to take a little break.
      logging.info('Just works! Creating the tarball. '
                   'This will take a while... meanwhile, go get %s. '
                   'You deserve it.',
                   (['some rest'] * 5 +
                    ['a cup of coffee'] * 7 +
                    ['some lunch', 'some fruit'] +
                    ['an afternoon snack'] * 2 +
                    ['a beer'] * 8)[time.localtime().tm_hour])

      output_file = self.bundle_dir + '.tar.bz2'
      Spawn(['tar', '-cf', output_file,
             '-I', file_utils.GetCompressor('bz2'),
             '-C', self.bundle_dir, '.'],
            log=True, check_call=True)
      logging.info(
          'Created %s (%.1f GiB).',
          output_file, os.path.getsize(output_file) / (1024. * 1024. * 1024.))

    logging.info('The README file (%s) has been updated.  Make sure to check '
                 'that it is correct!', self.readme_path)
    if sys_utils.InChroot() and self.build_board.factory_board_files:
      factory_board_bundle_path = os.path.join(
          self.build_board.factory_board_files, 'bundle')
    else:
      factory_board_bundle_path = 'factory-board'
    logging.info(
        "IMPORTANT: If you modified the README or MANIFEST.yaml, don't forget "
        'to check your changes into %s.',
        factory_board_bundle_path)

  @contextlib.contextmanager
  def _DownloadResource(self, possible_urls, resource_name=None):
    """Downloads a resource file from given URLs.

    This function downloads a resource from a list of possible URLs (only the
    first one found by the function will be downloaded). If no file is found at
    all possible URLs, an exception will be raised.

    Args:
      possible_urls: a single or a list of possible GS URLs to search.
      resource_name: a human readable name of the resource, just for logging,
          won't affect the behavior of downloading.
    """
    resource_name = resource_name or 'resource'

    if not isinstance(possible_urls, list):
      possible_urls = [possible_urls]

    found_url = None
    # ls to see if a given URL exists.
    for url in possible_urls:
      try:
        logging.info('Looking for %s at %s', resource_name, url)
        output = self.gsutil.LS(url)
      except gsutil.NoSuchKey:  # Not found; try next
        continue

      assert len(output) == 1, (
          'Expected %r to matched 1 files, but it matched %r', url, output)

      # Found. Download it!
      found_url = output[0].strip()
      break

    if found_url is None:
      raise Exception('No %s found in %r' % (resource_name, possible_urls))
    logging.info('Starting to download %s...', found_url)
    downloaded_path = self.gsutil.GSDownload(found_url)

    try:
      yield (downloaded_path, found_url)
    finally:
      TryUnlink(downloaded_path)

  def _DownloadAndExtractImage(self, image_name, possible_urls, target_dir):
    with self._DownloadResource(
        possible_urls, image_name) as (downloaded_path, found_url):
      try:
        file_utils.TryMakeDirs(target_dir)
        image_basename = os.path.basename(found_url)
        if image_basename.endswith('.bin'):  # just move
          dst_path = os.path.join(target_dir, image_basename)
          logging.info('Moving %r to %r', downloaded_path, dst_path)
          shutil.move(downloaded_path, dst_path)
        elif image_basename.endswith('.tar.xz'):
          logging.info('Extracting %s image into %s...', image_name, target_dir)
          file_utils.ExtractFile(downloaded_path, target_dir)

          extracted_path = os.listdir(target_dir)
          assert len(extracted_path) == 1, (
              'Expect only one file in %r but found multiple' % target_dir)
          extracted_path = os.path.join(target_dir, extracted_path[0])

          # Replace '.tar.xz' with the extracted ext name ('.bin' normally).
          unused_name, ext = os.path.splitext(extracted_path)
          dst_path = os.path.join(target_dir, image_basename[:-7] + ext)
          shutil.move(extracted_path, dst_path)
        else:
          raise ValueError(
              "Don't know how to handle file extension of %r" % downloaded_path)
        return dst_path
      finally:
        TryUnlink(downloaded_path)

  def _DownloadTestImage(self, requested_version, target_dir):
    possible_urls = []
    for channel in RESOURCE_CHANNELS:
      url = '%s/%s' % (
          FinalizeBundle._ResourceBaseURL(
              channel, self.build_board.gsutil_name, requested_version),
          '*test*.tar.xz')
      possible_urls.append(url)
    return self._DownloadAndExtractImage('test image', possible_urls,
                                         target_dir)

  def _DownloadReleaseImage(self, requested_version, target_dir):
    possible_urls = []
    # Signed recovery image ends with .bin and takes higher priority, so .bin
    # must be searched first. Unsigned recovery image ends with .tar.xz.
    for ext in ['.bin', '.tar.xz']:
      for channel in RESOURCE_CHANNELS:
        url = '%s/%s%s' % (
            FinalizeBundle._ResourceBaseURL(
                channel, self.build_board.gsutil_name, requested_version),
            '*recovery*', ext)
        possible_urls.append(url)
    return self._DownloadAndExtractImage('release image', possible_urls,
                                         target_dir)

  def _DownloadFactoryToolkit(self, requested_version, target_dir):
    possible_urls = []
    for channel in RESOURCE_CHANNELS:
      url = '%s/%s' % (
          FinalizeBundle._ResourceBaseURL(
              channel, self.build_board.gsutil_name, requested_version),
          '*factory*.zip')
      possible_urls.append(url)
    with self._DownloadResource(
        possible_urls, 'factory toolkit') as (downloaded_path, unused_url):
      file_utils.ExtractFile(downloaded_path, target_dir)

    return self._LocateOneResource(
        'factory toolkit', LOCAL, TOOLKIT_SEARCH_DIRS,
        lambda unused_path, unused_version: True)

  @staticmethod
  def _ResourceBaseURL(channel, board, version):
    return (
        'gs://chromeos-releases/%(channel)s-channel/%(board)s/%(version)s' %
        dict(channel=channel, board=board, version=version))

  @staticmethod
  def _ListAllFilesIn(search_dirs):
    """Returns all files under search_dirs.

    Args:
      search_dirs: a list of directories to search.
    """
    found_entries = []
    for d in search_dirs:
      if os.path.isdir(d):
        for f in os.listdir(d):
          p = os.path.join(d, f)
          if os.path.isfile(p):
            found_entries.append(p)
    return found_entries


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  FinalizeBundle().Main()
