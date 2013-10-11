#!/usr/bin/python -B
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import fnmatch
import glob
import logging
import os
import pipes
import re
import shutil
import subprocess
import sys
import time
import urlparse
import yaml
from distutils.version import LooseVersion
from pkg_resources import parse_version

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.tools.make_update_bundle import MakeUpdateBundle
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils.file_utils import (
    UnopenedTemporaryFile, CopyFileSkipBytes)
from cros.factory.utils.process_utils import Spawn, CheckOutput


GSUTIL_CACHE_DIR = os.path.join(os.environ['HOME'], 'gsutil_cache')

REQUIRED_GSUTIL_VERSION = [3, 32]  # 3.32

DELETION_MARKER_SUFFIX = '_DELETED'

def CheckDictHasOnlyKeys(dict_to_check, keys):
  """Makes sure that a dictionary's keys are valid.

  Args:
    dict_to_check: A dictionary.
    keys: The set of allowed keys in the dictionary.
  """
  if not isinstance(dict_to_check, dict):
    raise TypeError('Expected dict but found %s' % type(dict_to_check))

  extra_keys = set(dict_to_check) - set(keys)
  if extra_keys:
    raise ValueError('Found extra keys: %s' % list(extra_keys))


class Glob(object):
  """A glob containing items to include and exclude.

  Properties:
    include: A single pattern identifying files to include.
    exclude: Patterns identifying files to exclude.  This can be
      None, or a single pattern, or a list of patterns.
  """
  def __init__(self, include, exclude=None):
    self.include = include
    if exclude is None:
      self.exclude = []
    elif isinstance(exclude, list):
      self.exclude = exclude
    elif isinstance(exclude, str):
      self.exclude = [exclude]
    else:
      raise TypeError, 'Unexpected exclude type %s' % type(exclude)

  def Match(self, root):
    """Returns files that match include but not exclude.

    Args:
      root: Root within which to evaluate the glob.
    """
    ret = []
    for f in glob.glob(os.path.join(root, self.include)):
      if not any(fnmatch.fnmatch(f, os.path.join(root, pattern))
                 for pattern in self.exclude):
        ret.append(f)
    return ret

  @staticmethod
  def Construct(loader, node):
    """YAML constructor."""
    value = loader.construct_mapping(node)
    CheckDictHasOnlyKeys(value, ['include', 'exclude'])
    return Glob(value['include'], value.get('exclude', None))


def GSDownload(url):
  """Downloads a file from Google storage, returning the path to the file.

  Downloads are cached in GSUTIL_CACHE_DIR.

  Args:
    url: URL to download.

  Returns:
    Path to the downloaded file.  The returned path may have an arbitrary
    filename.
  """
  utils.TryMakeDirs(os.path.dirname(GSUTIL_CACHE_DIR))

  cached_path = os.path.join(GSUTIL_CACHE_DIR, url.replace('/', '!'))
  if os.path.exists(cached_path):
    logging.info('Using cached %s (%.1f MiB)',
                 url, os.path.getsize(cached_path) / (1024.*1024.))
    return cached_path

  in_progress_path = cached_path + '.INPROGRESS'
  Spawn(['gsutil', '-m', 'cp', url, 'file://' + in_progress_path],
        check_call=True, log=True)
  shutil.move(in_progress_path, cached_path)
  return cached_path


def GetReleaseVersion(mount_point):
  """Returns the release version of an image mounted at mount_point."""
  match = re.search(
      '^CHROMEOS_RELEASE_VERSION=(.+)$',
      open(os.path.join(mount_point, 'etc', 'lsb-release')).read(),
      re.MULTILINE)
  if not match:
    sys.exit('Unable to read lsb-release from %s' % mount_point)
  return match.group(1)


def GetFirmwareVersions(updater):
  """Returns the firmware versions in an updater.

  Args:
    updater: Path to a firmware updater.

  Returns:
    A tuple (bios_version, ec_version)
  """
  stdout = Spawn(
      [updater, '-V'], log=True, check_output=True).stdout_data

  versions = []
  for label in ['BIOS version', 'EC version']:
    match = re.search(
        '^' + label + ':\s+(.+)$', stdout, re.MULTILINE)
    if not match:
      sys.exit(
        'Unable to read %s from chromeos-firmwareupdater output %r' % (
            label, stdout))
    versions.append(match.group(1))
  return tuple(versions)


USAGE = """
Finalizes a factory bundle.  This script checks to make sure that the
bundle is valid, outputs version information into the README file, and
tars up the bundle.

The bundle directory (the DIR argument) must have a MANIFEST.yaml file
like the following:

  board: link
  self.bundle_name: 20121115_pvt
  mini_omaha_ip: 192.168.4.1
  # Files to download and add to the bundle.
  add_files:
  - install_into: release
    source: "gs://.../chromeos_recovery_image.bin"
  - install_into: firmware
    extract_files: [ec.bin, nv_image-link.bin]
    source: 'gs://.../ChromeOS-firmware-...tar.bz2'
  # Files to delete if present.
  delete_files:
  - install_shim/factory_install_shim.bin
  # Files that are expected to be in the bundle.
  files:
  - MANIFEST.yaml  # This file!
  - README
  - ...

The bundle must be in a directory named
factory_bundle_${board}_${self.bundle_name} (where board and self.bundle_name
are the same as above).
"""


class FinalizeBundle(object):
  """Finalizes a factory bundle (see USAGE).

  Properties:
    args: Command-line arguments from argparse.
    bundle_dir: Path to the bundle directory.
    bundle_name: Name of the bundle (e.g., 20121115_proto).
    factory_image_path: Path to the factory image in the bundle.
    board: Board name (e.g., link).
    simple_board: For board name like "base_variant", simple_board is "variant".
      simple_board == board if board is not a variant board.
      This name is used in firmware and hwid.
    manifest: Parsed YAML manifest.
    expected_files: List of files expected to be in the bundle (relative paths).
    all_files: Set of files actually present in the bundle (relative paths).
    readme_path: Path to the README file within the bundle.
    factory_image_base_version: Build of the factory image (e.g., 3004.100.0)
    release_image_path: Path to the release image.
    install_shim_version: Build of the install shim.
    netboot_install_shim_version: Build of the netboot install shim.
    mini_omaha_script_path: Path to the script used to start the mini-Omaha
      server.
    new_factory_par: Path to a replacement factory.par.
  """
  args = None
  bundle_dir = None
  bundle_name = None
  factory_image_path = None
  board = None
  simple_board = None
  manifest = None
  expected_files = None
  all_files = None
  readme_path = None
  factory_image_base_version = None
  install_shim_version = None
  netboot_install_shim_version = None
  release_image_path = None
  mini_omaha_script_path = None
  new_factory_par = None

  def Main(self):
    if not utils.in_chroot():
      sys.exit('Please run this script from within the chroot.')

    self.ParseArgs()
    self.LoadManifest()
    self.Download()
    self.DeleteFiles()
    self.UpdateMiniOmahaURL()
    self.PatchImage()
    self.ModifyFactoryImage()
    self.SetWipeOption()
    self.MakeUpdateBundle()
    self.MakeFactoryPackages()
    self.FixFactoryPar()
    self.CheckFiles()
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
        '--no-updater', dest='updater', action='store_false',
        help="Don't make an update bundle (for testing only)")
    parser.add_argument(
        '--no-archive', dest='archive', action='store_false',
        help="Don't make a tarball (for testing only)")
    parser.add_argument(
        '--no-make-factory-packages', dest='make_factory_package',
        action='store_false',
        help="Don't call make_factory_package (for testing only)")
    parser.add_argument(
        '--complete-script', dest='complete_script',
        help=('Filename of complete script used for make_factory_package. '
              'Empty means no complete script is used.'),
        default='complete_script_sample.sh')
    parser.add_argument(
        '--tip-of-branch', dest='tip_of_branch', action='store_true',
        help="Use tip version of release image, install shim, and "
             "netboot install shim on the branch (for testing only)")
    parser.add_argument(
        '--test-list', dest='test_list', metavar='TEST_LIST',
        help="Set active test_list. e.g. --test-list manual_smt to set active "
             "test_list to test_list.manual_smt")
    parser.add_argument(
        '--patch', action='store_true',
        help=('Invoke patch_image before finalizing (requires '
              'patch_image_args in MANIFEST.yaml)'))
    parser.add_argument(
        '--patch-image-extra-args',
        help='Extra arguments for patch_image')

    parser.add_argument(
        'dir', metavar='DIR',
        help="Directory containing the bundle")
    self.args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    self.bundle_dir = os.path.realpath(self.args.dir)

  def LoadManifest(self):
    yaml.add_constructor('!glob', Glob.Construct)
    self.manifest = yaml.load(open(
        os.path.join(self.args.dir, 'MANIFEST.yaml')))
    CheckDictHasOnlyKeys(
        self.manifest, ['board', 'bundle_name', 'add_files', 'delete_files',
                        'add_files_to_image', 'delete_files_from_image',
                        'site_tests', 'wipe_option', 'files', 'mini_omaha_url',
                        'patch_image_args'])

    self.board = self.manifest['board']
    self.simple_board = self.board.split('_')[-1]

    self.bundle_name = self.manifest['bundle_name']
    if not re.match(r'^\d{8}_', self.bundle_name):
      sys.exit("The self.bundle_name (currently %r) should be today's date, "
               "plus an underscore, plus a description of the build, e.g.: %r" %
               (self.bundle_name, time.strftime("%Y%m%d_proto")))

    expected_dir_name = 'factory_bundle_' + self.board + '_' + self.bundle_name
    if expected_dir_name != os.path.basename(self.bundle_dir):
      sys.exit(
        'bundle_name in manifest is %s, so directory name should be %s, '
        'but it is %s' % (
            self.bundle_name, expected_dir_name,
            os.path.basename(self.bundle_dir)))

    self.expected_files = set(map(self._SubstVars, self.manifest['files']))
    self.factory_image_path = os.path.join(
        self.bundle_dir, 'factory_test', 'chromiumos_factory_image.bin')
    with MountPartition(self.factory_image_path, 3) as mount:
      self.factory_image_base_version = GetReleaseVersion(mount)
    self.readme_path = os.path.join(self.bundle_dir, 'README')

  def CheckGSUtilVersion(self):
    # Check for gsutil >= 3.32.
    process = Spawn(['gsutil', 'version'],
                    read_stderr=True, read_stdout=True)
    if ("No such file or directory: '/usr/lib64/gsutil/CHECKSUM'" in
        process.stderr_data):
      # Sigh... workaround install bug
      version = open('/usr/lib/gsutil/VERSION').read()
    else:
      # The version output changed from stderr to stdout in later
      # versions of gsutil.
      match = re.search('^gsutil version (.+)',
                        process.stderr_data + '\n' + process.stdout_data,
                        re.MULTILINE)
      assert match, ('Unable to parse "gsutil version" output: %r' %
                     process.stderr_data)
      version = match.group(1)

    # Remove 'pre...' string at the end, if any
    version = re.sub('pre.*', '', version)
    version_split = [int(x) for x in version.split('.')]
    if version_split < REQUIRED_GSUTIL_VERSION:
      sys.exit(
          'gsutil version >=%s is required; you seem to have %s.\n'
          'Please download and install gsutil ('
          'https://developers.google.com/storage/docs/gsutil_install), and '
          'make sure this is in your PATH before the system gsutil.'  % (
              '.'.join(str(x) for x in REQUIRED_GSUTIL_VERSION), version))

  def Download(self):
    # Make sure gsutil is up to date; older versions are pretty broken.
    self.CheckGSUtilVersion()

    if not 'add_files' in self.manifest:
      return

    for f in self.manifest['add_files']:
      CheckDictHasOnlyKeys(f, ['install_into', 'source', 'extract_files'])
      dest_dir = os.path.join(self.bundle_dir, f['install_into'])
      utils.TryMakeDirs(dest_dir)

      if self.args.tip_of_branch:
        f['source'] = self._SubstVars(f['source'])
        self._ChangeTipVersion(f)

      source = self._SubstVars(f['source'])

      if self.args.download:
        cached_file = GSDownload(source)

      if f.get('extract_files'):
        # Gets netboot install shim version from source url since version
        # is not stored in the image.
        if any('vmlinux.uimg' in extract_file
               for extract_file in f['extract_files']):
          self.netboot_install_shim_version = str(LooseVersion(
              os.path.basename(os.path.dirname(source))))
        install_into = os.path.join(self.bundle_dir, f['install_into'])
        if self.args.download:
          if cached_file.endswith('.zip'):
            Spawn(['unzip', '-o', cached_file,
                   '-d', install_into] +
                  f['extract_files'],
                  log=True, check_call=True)
          else:
            Spawn(['tar', '-xvvf', cached_file,
                   '-C', install_into] +
                  f['extract_files'],
                  log=True, check_call=True)
        for f in f['extract_files']:
          self.expected_files.add(os.path.relpath(os.path.join(install_into, f),
                                             self.bundle_dir))
      else:
        dest_path = os.path.join(dest_dir, os.path.basename(source))
        if self.args.download:
          shutil.copyfile(cached_file, dest_path)
        self.expected_files.add(os.path.relpath(dest_path, self.bundle_dir))

  def _ChangeTipVersion(self, add_file):
    """Changes image to the latest version for testing tip of branch.

    Changes install shim, release image, netboot install shim(vmlinux.uimg) to
    the latest version of original branch for testing. Check _GSGetLatestVersion
    for the detail of choosing the tip version on the branch.
    """
    if add_file['install_into'] in ['factory_shim', 'release']:
      latest_source = self._GSGetLatestVersion(add_file['source'])
      logging.info('Changing %s source from %s to %s for testing tip of branch',
                   add_file['install_into'], add_file['source'], latest_source)
      self._CheckFileExistsOrDie(add_file['install_into'], latest_source)
      add_file['source'] = latest_source
    if (add_file.get('extract_files') and
        any('vmlinux.uimg' in f for f in add_file['extract_files'])):
      latest_source = self._GSGetLatestVersion(add_file['source'])
      logging.info('Changing vmlinux.uimg source from %s to %s for testing '
                   'tip of branch', add_file['source'], latest_source)
      self._CheckFileExistsOrDie('vmlinux.uimg', latest_source)
      add_file['source'] = latest_source

  def _CheckFileExistsOrDie(self, image, url):
    if not self._GSFileExists(url):
      sys.exit(('The %s image source on tip of branch is not there, '
                '%s does not exist. Perhaps buildbot is still building it '
                'or build failed?' % (image, url)))

  def _GSFileExists(self, url):
    try:
      Spawn(['gsutil', '-m', 'ls', url], check_call=True)
    except subprocess.CalledProcessError:
      return False
    else:
      return True

  def _GSGetLatestVersion(self, url):
    """Gets the latest version of image on the branch of url.
    Finds the latest version of image on the branch specified in url.
    This function only cares if input image is on master branch or not.
    If input image has a zero minor version, it is on master branch.
    For input image on master branch, the function returns the url of the
    latest image on master branch. For input image not on master branch,
    this function returns the url of the image with the same major version
    and the largest minor version. For example, there are these images
    available:

    4100.0.0 (On master branch)
      4100.1.0  (Start of 4100.B branch)
      ...
      4100.38.0
        4100.38.1  (Start of 4100.38.B branch)
        ...
        4100.38.5
        4100.38.6
      4100.39.0
    4101.0.0
    ...
    4120.0.0
      4120.1.0  (Start of 4120.B branch)
      4120.2.0

    Example    input       output      Description
           4100.0.0       4120.0.0    On master branch.
           4100.1.0       4100.39.0   On 4100.B branch.
           4100.38.0      4100.39.0   On 4100.B branch.
           4100.38.5      4100.39.0   On 4100.38.B branch but we decide
                                      4100.39.0 and 4100.38.6 should be
                                      compared together as sub-branch of 4100.B.
           4101.0.0       4120.0.0    On master branch.
           4120.1.0       4120.2.0    On 4120.B branch.
    """
    # Use LooseVersion instead of StrictVersion because we want to preserve the
    # trailing 0 like 4100.0.0 instead of truncating it to 4100.0.
    version = LooseVersion(os.path.basename(os.path.dirname(url)))
    parsed_version = parse_version(str(version))
    major_version = parsed_version[0]
    minor_version = parsed_version[1] if len(parsed_version) > 2 else None
    board_directory = os.path.dirname(os.path.dirname(url))
    version_url_list = CheckOutput(['gsutil', '-m', 'ls', board_directory],
                                   check_call=True).splitlines()
    latest_version = version
    for version_url in version_url_list:
      version_url = version_url.rstrip('/')
      candidate_version = LooseVersion(os.path.basename(version_url))
      parsed_candidate_version = parse_version(str(candidate_version))
      major_candidate_version = parsed_candidate_version[0]
      minor_candidate_version = (parsed_candidate_version[1]
                                 if len(parsed_candidate_version) > 2 else None)
      if minor_version and major_candidate_version != major_version:
        continue
      if not minor_version and minor_candidate_version:
        continue
      if candidate_version > latest_version:
        latest_version = candidate_version
    return url.replace(str(version), str(latest_version))

  def DeleteFiles(self):
    if not 'delete_files' in self.manifest:
      return
    for f in self.manifest['delete_files']:
      path = os.path.join(self.bundle_dir, f)
      if os.path.exists(path):
        os.unlink(path)

  def PatchImage(self):
    if not self.args.patch:
      return

    patch_image_args = self.manifest.get('patch_image_args')
    if not patch_image_args:
      sys.exit('--patch flag was specified, but MANIFEST.yaml has no '
               'patch_image_args')

    factory_par_path = os.path.join(
        '/build', self.manifest['board'],
        'usr', 'local', 'factory', 'bundle', 'shopfloor', 'factory.par')

    factory_par_time_old = os.stat(factory_par_path).st_mtime

    patch_command = ([os.path.join(factory.FACTORY_PATH, 'bin', 'patch_image'),
                      '--input', self.factory_image_path,
                      '--output', 'IN_PLACE'] +
                     patch_image_args.split(' ') +
                     (self.args.patch_image_extra_args.split(' ')
                      if self.args.patch_image_extra_args else []))
    Spawn(patch_command, log=True, check_call=True)

    factory_par_time_new = os.stat(factory_par_path).st_mtime
    if factory_par_time_old != factory_par_time_new:
      logging.info('%s has changed; will replace factory.par in bundle',
                   factory_par_path)
      self.new_factory_par = factory_par_path

  def ModifyFactoryImage(self):
    add_files_to_image = self.manifest.get('add_files_to_image', [])
    delete_files_from_image = self.manifest.get('delete_files_from_image', [])
    if add_files_to_image or delete_files_from_image:
      with MountPartition(self.factory_image_path, 1, rw=True) as mount:
        for f in add_files_to_image:
          dest_dir = os.path.join(mount, 'dev_image', f['install_into'])
          Spawn(['mkdir', '-p', dest_dir], log=True, sudo=True, check_call=True)
          Spawn(['cp', '-a', os.path.join(self.bundle_dir, f['source']),
                 dest_dir], log=True, sudo=True, check_call=True)

        to_delete = []
        for f in delete_files_from_image:
          if isinstance(f, Glob):
            to_delete.extend(f.Match(mount))
          else:
            path = os.path.join(mount, f)
            if os.path.exists(path):
              to_delete.append(path)

        for f in sorted(to_delete):
          # For every file x we delete, we'll leave a file called
          # 'x_DELETED' so that it's clear why the file is missing.
          # But we don't want to delete any of these marker files!
          if f.endswith(DELETION_MARKER_SUFFIX):
            continue
          Spawn('echo Deleted by finalize_bundle > %s' %
                pipes.quote(f + DELETION_MARKER_SUFFIX),
                sudo=True, shell=True, log=True,
                check_call=True)
          Spawn(['rm', '-rf', f], sudo=True, log=True)

        # Write and delete a giant file full of zeroes to clear
        # all the blocks that we've just deleted.
        zero_file = os.path.join(mount, 'ZERO')
        # This will fail eventually (no space left on device)
        Spawn(['dd', 'if=/dev/zero', 'of=' + zero_file, 'bs=1M'],
              sudo=True, call=True, log=True, ignore_stderr=True)
        Spawn(['rm', zero_file], sudo=True, log=True, check_call=True)

    # Removes unused site_tests
    # suite_Factory must be preserved for /usr/local/factory/custom symlink.
    site_tests = self.manifest.get('site_tests')
    if site_tests is not None:
      site_tests.append('suite_Factory')
      with MountPartition(self.factory_image_path, 1, rw=True) as mount:
        site_tests_dir = os.path.join(mount, 'dev_image', 'autotest',
                                      'site_tests')
        for name in os.listdir(site_tests_dir):
          path = os.path.join(site_tests_dir, name)
          if name not in site_tests:
            Spawn(['rm', '-rf', path], log=True, sudo=True, check_call=True)

    if self.args.test_list:
      logging.info('Setting active test_list to test_list.%s',
                   self.args.test_list)
      with MountPartition(self.factory_image_path, 1, rw=True) as mount:
        test_list_py = os.path.join(mount, 'dev_image', 'factory', 'py', 'test',
                                    'test_lists', 'test_lists.py')
        if os.path.isfile(test_list_py):
          logging.info('Using test_list v2 ACTIVE file')
          active = os.path.join(mount, 'dev_image', 'factory', 'py', 'test',
                                'test_lists', 'ACTIVE')
          with open(active, 'w') as f:
            f.write(self.args.test_list)
        else:
          logging.info('Using test_list v1 active symlink')
          test_list = 'test_list.%s' % self.args.test_list
          active = os.path.join(mount, 'dev_image', 'factory', 'test_lists',
                                'active')
          Spawn(['ln', '-sf', test_list, active], log=True, sudo=True,
                check_call=True)

  def SetWipeOption(self):
    wipe_option = self.manifest.get('wipe_option', [])
    if wipe_option:
      assert len(wipe_option) == 1, 'There should be one wipe_option.'
      option = wipe_option[0]
      assert option in ['shutdown', 'battery_cut_off', 'reboot']
      # No need to write option if option is reboot.
      if option == 'reboot':
        return
      with MountPartition(self.factory_image_path, 1, rw=True) as mount:
        wipe_option_path = os.path.join(mount, 'factory_wipe_option')
        self._WriteWithSudo(wipe_option_path, option)

  def _WriteWithSudo(self, file_path, content):
    """Writes content to file_path with sudo=True."""
    # Write with sudo, since only root can write this.
    process = Spawn('cat > %s' % pipes.quote(file_path),
                    sudo=True, stdin=subprocess.PIPE, shell=True)
    process.stdin.write(content)
    process.stdin.close()
    if process.wait():
      sys.exit('Unable to write %s' % file_path)

  def MakeUpdateBundle(self):
    # Make the factory update bundle
    if self.args.updater:
      updater_path = os.path.join(
          self.bundle_dir, 'shopfloor', 'shopfloor_data', 'update',
          'factory.tar.bz2')
      utils.TryMakeDirs(os.path.dirname(updater_path))
      MakeUpdateBundle(self.factory_image_path, updater_path)

  def UpdateMiniOmahaURL(self):
    mini_omaha_url = self.manifest.get('mini_omaha_url')
    if not mini_omaha_url:
      return

    def PatchLSBFactory(mount):
      """Patches lsb-factory in an image.

      Returns:
        True if there were any changes.
      """
      lsb_factory_path = os.path.join(
          mount, 'dev_image', 'etc', 'lsb-factory')
      logging.info('Patching URLs in %s', lsb_factory_path)
      orig_lsb_factory = open(lsb_factory_path).read()
      lsb_factory, number_of_subs = re.subn(
          '(?m)^(CHROMEOS_(AU|DEV)SERVER=).+$', r'\1' + mini_omaha_url,
          orig_lsb_factory)
      if number_of_subs != 2:
        sys.exit('Unable to set mini-Omaha server in %s' % lsb_factory_path)
      if lsb_factory == orig_lsb_factory:
        return False  # No changes
      self._WriteWithSudo(lsb_factory_path, lsb_factory)
      return True

    def PatchInstallShim(shim):
      """Updates mini_omaha_url in install shim.

      It also updates self.install_shim_version.
      """
      def GetSigningKey(shim):
        """Derives signing key from factory install shim's file name."""
        if shim.endswith('factory_install_shim.bin'):
          return 'unsigned'
        key_match = re.search('_(\w+)\.bin$', shim)
        if key_match:
          return key_match.group(1)
        else:
          # Error deriving signing key
          return 'undefined'

      with MountPartition(shim, 1, rw=True) as mount:
        PatchLSBFactory(mount)

      with MountPartition(shim, 3) as mount:
        self.install_shim_version = '%s (%s)' % (GetReleaseVersion(mount),
                                                 GetSigningKey(shim))

    def UpdateNetbootURL():
      """Updates Omaha & TFTP servers' URL in netboot firmware.

      It takes care of both uboot and depthcharge firmware, if presents.
      """
      UpdateUbootNetboot()
      UpdateDepthchargeNetboot()

    def UpdateUbootNetboot():
      """Updates Omaha & TFTP servers' URL in uboot netboot firmware."""
      netboot_firmware_image = os.path.join(
          self.bundle_dir, 'netboot_firmware',
          'nv_image-%s.bin' % self.simple_board)
      if os.path.exists(netboot_firmware_image):
        update_firmware_vars = os.path.join(
            self.bundle_dir, 'factory_setup', 'update_firmware_vars.py')
        new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
        Spawn([update_firmware_vars,
               '--force',
               '-i', netboot_firmware_image,
               '-o', new_netboot_firmware_image,
               '--omahaserver=%s' % mini_omaha_url,
               '--tftpserverip=%s' %
                 urlparse.urlparse(mini_omaha_url).hostname],
              check_call=True, log=True)
        shutil.move(new_netboot_firmware_image, netboot_firmware_image)

    def UpdateDepthchargeNetboot():
      """Updates Omaha & TFTP servers' URL in depthcharge netboot firmware.

      Also copy 'vmlinux.uimg', skips the first 64 bytes and stored it
      as 'vmlinux.bin'.
      """
      netboot_firmware_image = os.path.join(
          self.bundle_dir, 'netboot_firmware', 'image.net.bin')
      if os.path.exists(netboot_firmware_image):
        update_firmware_settings = os.path.join(
            self.bundle_dir, 'factory_setup', 'update_firmware_settings.py')
        new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
        Spawn([update_firmware_settings,
               '--clobber',
               '--input', netboot_firmware_image,
               '--output', new_netboot_firmware_image,
               '--omahaserver=%s' % mini_omaha_url,
               '--tftpserverip=%s' %
                 urlparse.urlparse(mini_omaha_url).hostname],
              check_call=True, log=True)
        shutil.move(new_netboot_firmware_image, netboot_firmware_image)

        # The default name of netboot image is changed to 'vmlinux.bin'.
        # Also, we need to copy vmlinux.uimg to vmlinux.bin and skip
        # the first 64 bytes.
        # Keep both of the files so everyone can be aware of the difference.
        netboot_image = os.path.join(self.bundle_dir, 'factory_shim',
                                     'netboot', 'vmlinux.uimg')
        new_netboot_image = os.path.join(self.bundle_dir, 'factory_shim',
                                         'netboot', 'vmlinux.bin')
        CopyFileSkipBytes(netboot_image, new_netboot_image, 64)

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

    # Take care of the netboot initrd as well, if present.
    netboot_image = os.path.join(self.bundle_dir, 'factory_shim',
                                 'netboot', 'initrd.uimg')
    if os.path.exists(netboot_image):
      with UnopenedTemporaryFile(prefix='rootfs.') as rootfs:
        with open(netboot_image) as netboot_image_in:
          with open(rootfs, 'w') as rootfs_out:
            logging.info('Unpacking initrd rootfs')
            netboot_image_in.seek(64)
            Spawn(
                ['gunzip', '-c'],
                stdin=netboot_image_in, stdout=rootfs_out, check_call=True)
        with MountPartition(rootfs, rw=True) as mount:
          lsb_factory_changed = PatchLSBFactory(
              os.path.join(mount, 'mnt', 'stateful_partition'))

        if lsb_factory_changed:
          # Success!  Zip it back up.
          with UnopenedTemporaryFile(prefix='rootfs.') as rootfs_gz:
            with open(rootfs_gz, 'w') as out:
              Spawn(['pigz', '-9c', rootfs], stdout=out, log=True, call=True)

            new_netboot_image = netboot_image + '.INPROGRESS'
            Spawn(['mkimage', '-A', 'x86', '-O', 'linux', '-T', 'ramdisk',
                   '-a', '0x12008000', '-n', 'Factory Install RootFS',
                   '-C', 'gzip', '-d', rootfs_gz, new_netboot_image],
                  check_call=True, log=True)
            shutil.move(new_netboot_image, netboot_image)

    UpdateNetbootURL()

  def MakeFactoryPackages(self):
    release_images = glob.glob(os.path.join(self.bundle_dir, 'release/*.bin'))
    if len(release_images) != 1:
      sys.exit("Expected one release image but found %d" % len(release_images))
    self.release_image_path = release_images[0]

    factory_setup_dir = os.path.join(self.bundle_dir, 'factory_setup')
    make_factory_package = [
        './make_factory_package.sh',
        '--board', self.board,
        '--release', os.path.relpath(self.release_image_path,
                                     factory_setup_dir),
        '--factory', '../factory_test/chromiumos_factory_image.bin',
        '--hwid_updater', '../hwid/hwid_v3_bundle_%s.sh' %
                          self.simple_board.upper()]
    if self.args.complete_script:
      make_factory_package.extend([
          '--complete_script', self.args.complete_script])

    firmware_updater = os.path.join(
        self.bundle_dir, 'firmware', 'chromeos-firmwareupdate')
    if os.path.exists(firmware_updater):
      make_factory_package += [
          '--firmware_updater', os.path.relpath(
              firmware_updater, factory_setup_dir)]

    if self.args.make_factory_package:
      Spawn(make_factory_package, cwd=factory_setup_dir,
            check_call=True, log=True)

    # Build the mini-Omaha startup script.
    self.mini_omaha_script_path = os.path.join(
        self.bundle_dir, 'start_download_server.sh')
    if os.path.exists(self.mini_omaha_script_path):
      os.unlink(self.mini_omaha_script_path)
    with open(self.mini_omaha_script_path, 'w') as f:
      f.write('\n'.join([
          '#!/bin/bash',
          'set -e',  # Fail on error
          'cd $(dirname $(readlink -f "$0"))/factory_setup',
          'cat static/miniomaha.conf',
          ('echo Miniomaha configuration MD5SUM: '
           '$(md5sum static/miniomaha.conf)'),
          'echo Validating configuration...',
          ('python miniomaha.py --validate_factory_config'),
          'echo Starting download server.',
          'python miniomaha.py',
          ''  # Add newline at EOF
          ]))
      os.fchmod(f.fileno(), 0555)

  def FixFactoryPar(self):
    """Fix symlinks to factory.par, and replace factory.par if necessary.

    (Certain files may have been turned into real files by the buildbots.)
    """
    factory_par_path = os.path.join(self.bundle_dir,
                                    'shopfloor', 'factory.par')
    with open(factory_par_path) as f:
      factory_par_data = f.read()

    # Look for files that are identical copies of factory.par.
    for root, dummy_dirs, files in os.walk(self.bundle_dir):
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
        os.symlink(os.path.relpath(factory_par_path,
                                   os.path.dirname(path)),
                   path)

    if self.new_factory_par:
      logging.info('Copying %s to %s', self.new_factory_par, factory_par_path)
      shutil.copy2(self.new_factory_par, factory_par_path)

  def CheckFiles(self):
    # Check that the set of files is correct
    self.all_files = set()
    for root, dirs, files in os.walk(self.bundle_dir):
      for f in files:
        # Remove backup files and compiled Python files.
        if f.endswith('~') or f.endswith('.pyc'):
          os.unlink(os.path.join(root, f))
          continue
        self.all_files.add(
            os.path.relpath(os.path.join(root, f), self.bundle_dir))
      for d in dirs:
        # Remove any empty directories
        try:
          os.rmdir(d)
        except OSError:
          pass

    missing_files = self.expected_files - self.all_files
    extra_files = self.all_files - self.expected_files
    if missing_files:
      logging.error('Missing files in bundle: %s',
                    ' '.join(sorted(missing_files)))
      logging.error("If the files really shouldn't be there, remove them from "
                    'the "files" section in MANIFEST.yaml')
    if extra_files:
      logging.error('Unexpected extra files in bundle: %s',
                    ' '.join(sorted(extra_files)))
      logging.error('If the files are really expected, '
                    'add them to the "files" section of MANIFEST.yaml')
    if missing_files or extra_files:
      sys.exit('Incorrect file set; terminating')

  def UpdateReadme(self):
    # Grok the README file; we'll be modifying it.
    readme_sections = re.findall(
        # Section header
        r'(\*\*\*\n\*\n\* (.+?)\n\*\n\*\*\*\n)'
        # Anything up to (but not including) the next section header
        r'((?:(?!\*\*\*).)+)', open(self.readme_path).read(), re.DOTALL)
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
        sys.exit("README is missing %s section" % k)

    # Make sure that the CHANGES section contains this version.
    expected_str = '%s changes:' % self.bundle_name
    if expected_str not in readme_sections[readme_section_index['CHANGES']][2]:
      sys.exit('The string %r was not found in the CHANGES section. '
               'Please add a section for it (if this is the first '
               'version, just say "initial release").' % expected_str)

    # Get some vital information
    vitals = [
        ('Board', self.board),
        ('Bundle', '%s (created by %s, %s)' % (
            self.bundle_name, os.environ['USER'],
            time.strftime('%a %Y-%m-%d %H:%M:%S %z')))]
    vitals.append(('Factory image base', self.factory_image_base_version))
    with MountPartition(self.factory_image_path, 1) as f:
      vitals.append(('Factory updater MD5SUM', open(
          os.path.join(f, 'dev_image/factory/MD5SUM')).read().strip()))
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
    if self.netboot_install_shim_version:
      vitals.append(('Netboot install shim (vmlinux.uimg)',
                     self.netboot_install_shim_version))
    with MountPartition(self.release_image_path, 3) as f:
      vitals.append(('Release (FSI)', GetReleaseVersion(f)))
      bios_version, ec_version = GetFirmwareVersions(
          os.path.join(f, 'usr/sbin/chromeos-firmwareupdate'))
      vitals.append(('Release (FSI) BIOS', bios_version))
      vitals.append(('Release (FSI) EC', ec_version))

    # If we have any firmware in the tree, add them to the vitals.
    firmwareupdates = []
    for f in self.all_files:
      path = os.path.join(self.bundle_dir, f)
      if os.path.basename(f) == 'chromeos-firmwareupdate':
        firmwareupdates.append(path)
        bios_version, ec_version = GetFirmwareVersions(path)
        vitals.append(('%s BIOS' % f, bios_version))
        vitals.append(('%s EC' % f, ec_version))
      elif os.path.basename(f) == 'ec.bin':
        # This is tricky, but it's the best we can do for now.  Look for a
        # line like "link_v1.2.34-56789a 2012-10-01 12:34:56 @build70-m2"
        strings = Spawn(['strings', path], check_output=True).stdout_data
        match = re.search('^(' + self.simple_board + '.+@.+)$',
                          strings, re.MULTILINE)
        if not match:
          sys.exit('Unable to find EC version in %s' % path)
        vitals.append((f, match.group(1)))
      elif os.path.basename(f).startswith('nv_image'):
        strings = Spawn(['strings', path], check_output=True).stdout_data
        match = re.search('^(Google_' + self.simple_board +
                          r'\.\d+\.\d+\.\d+)$',
                          strings, re.MULTILINE | re.IGNORECASE)
        if not match:
          sys.exit('Unable to find BIOS version in %s' % path)
        vitals.append((f, match.group(1)))

    vital_lines = []
    max_key_length = max(len(k) for k, v in vitals)
    for k, v in vitals:
      vital_lines.append("%s:%s %s" % (k, ' ' * (max_key_length - len(k)), v))
    vital_contents = '\n'.join(vital_lines)
    readme_sections[readme_section_index['VITAL INFORMATION']][2] = (
        vital_contents + '\n\n')

    index = readme_section_index.get('MINI-OMAHA SERVER')
    if index is not None:
      instructions = [
          'To start a mini-Omaha server:',
          '',
          '  ./start_download_server.sh'
          ]
      readme_sections[index][2] = (
          '\n'.join(instructions) + '\n\n')

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

      for mini in [True, False]:
        output_file = self.bundle_dir + ('.mini' if mini else '') + '.tar.bz2'
        Spawn(['tar', '-cf', output_file,
               '-I', 'pbzip2',
               '-C', os.path.dirname(self.bundle_dir)] +
              (['--exclude', '*.bin'] if mini else []) +
              [os.path.basename(self.bundle_dir)],
              log=True, check_call=True)
        logging.info(
            'Created %s (%.1f GiB).',
            output_file, os.path.getsize(output_file) / (1024.*1024.*1024.))

    logging.info('The README file (%s) has been updated.  Make sure to check '
                 'that it is correct!', self.readme_path)
    logging.info(
        "IMPORTANT: If you modified the README or MANIFEST.yaml, don't forget "
        "to check your changes into %s.",
        os.path.join(os.environ['CROS_WORKON_SRCROOT'],
                     'src', 'private-overlays', 'overlay-link-private',
                     'chromeos-base', 'chromeos-factory-board',
                     'files', 'bundle'))

  def _SubstVars(self, input_str):
    """Substitutes variables into a string.

    The following substitutions are made:
      ${BOARD} -> the simple board name (in uppercase)
      ${FACTORY_IMAGE_BASE_VERSION} -> the factory image version
    """
    subst_vars = {
        'BOARD': self.simple_board.upper(),
        'FACTORY_IMAGE_BASE_VERSION': self.factory_image_base_version
        }
    return re.sub(r'\$\{(\w+)\}', lambda match: subst_vars[match.group(1)],
                  input_str)


if __name__ == '__main__':
  FinalizeBundle().Main()
