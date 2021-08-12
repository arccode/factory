#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tools to finalize a factory bundle."""

import argparse
import concurrent.futures
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
from typing import Set
import urllib.parse

import yaml

from cros.factory.tools import get_version
from cros.factory.tools import gsutil
from cros.factory.utils import cros_board_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils import sys_utils
from cros.factory.utils.sys_utils import MountPartition
from cros.factory.utils.type_utils import CheckDictKeys


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

REQUIRED_GSUTIL_VERSION = [3, 32]  # 3.32

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
# Special string to find designs from Boxster config.
BOXSTER_DESIGNS = 'boxster_designs'


# Legacy: resources may live in different places due to historical reason. To
# maintain backward compatibility, we have to search for a set of directories.
# TODO(crbug.com/706756): once we completely remove the old directories, we can
#                         simple make this a string instead of a list of
#                         strings.
TEST_IMAGE_SEARCH_DIRS = ['test_image', 'factory_test']
RELEASE_IMAGE_SEARCH_DIRS = ['release_image', 'release']
TOOLKIT_SEARCH_DIRS = ['toolkit', 'factory_toolkit']
FACTORY_SHIM_SEARCH_DIR = 'factory_shim'

FIRMWARE_SEARCH_DIR = 'firmware'
# temporary directory for the release image which contains firmware
FIRMWARE_IMAGE_SOURCE_DIR = 'firmware_image_source'

# When version is fixed, we'll try to find the resource in the following order.
RESOURCE_CHANNELS = ['stable', 'beta', 'dev', 'canary']

PROJECT_TOOLKIT_PACKAGES = 'factory_project_toolkits.tar.gz'


class FinalizeBundleException(Exception):
  pass


def _GetReleaseVersion(mount_point):
  """Returns the release version of an image mounted at mount_point."""
  result = get_version.GetReleaseVersion(mount_point)
  if not result:
    raise FinalizeBundleException(
        'Unable to read lsb-release from %s' % mount_point)
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
      raise FinalizeBundleException(
          'Unable to read %r version from %s' % (label, updater))
  return versions


def _GetImageTool():
  factory_par = sys_utils.GetRunningFactoryPythonArchivePath()
  if factory_par is not None:
    return [factory_par, 'image_tool']
  if os.path.exists(os.path.join(SCRIPT_DIR, 'image_tool')):
    return [os.path.join(SCRIPT_DIR, 'image_tool')]
  if os.path.exists(os.path.join(SCRIPT_DIR, 'image_tool.py')):
    return [os.path.join(SCRIPT_DIR, 'image_tool.py')]
  raise FinalizeBundleException('Cannot find image_tool')


USAGE = """
Finalizes a factory bundle.  This script checks to make sure that the
bundle is valid, outputs version information into the README file, and
tars up the bundle.

The input is a MANIFEST.yaml file like the following:

  board: link
  project: link
  designs:
    - link
    - link_variant
  bundle_name: 20121115_pvt

  # Specify the version of test image directly.
  test_image: 9876.0.0

  # Specify that a local release image should be used.
  release_image: local

  # Specify the version of factory toolkit directly.
  toolkit: 9678.12.0
"""


class FinalizeBundle:
  """Finalizes a factory bundle (see USAGE).

  Properties:
    args: Command-line arguments from argparse.
    bundle_dir: Path to the bundle directory.
    bundle_name: Name of the bundle (e.g., 20121115_proto).
    build_board: The BuildBoard object for the board.
    board: Board name (e.g., link).
    project: Project name.
    designs: Design names, which are used as the index in firmware updater.
    manifest: Parsed YAML manifest.
    readme_path: Path to the README file within the bundle.
    install_shim_version: Build of the install shim.
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
    work_dir: Working directory.
    download: True to download files from Google Storage (for testing only).
    archive: True to make a tarball (for testing only).
    firmware_source: Source (LOCAL, 'release_image' or
        'release_image/xxxx.yy.zz') of the firmware.
    firmware_image_source: Path to the release image which contains
        the firmware.
  """
  bundle_dir = None
  bundle_name = None
  build_board = None
  board = None
  manifest = None
  readme_path = None
  install_shim_version = None
  project = None
  designs = None
  test_image_source = None
  test_image_path = None
  test_image_version = None
  release_image_source = None
  release_image_path = None
  release_image_version = None
  toolkit_source = None
  toolkit_path = None
  toolkit_version = None
  signed_shim_path = None
  gsutil = None
  has_firmware = DEFAULT_FIRMWARES
  work_dir = None
  download = None
  archive = None
  firmware_source = None
  firmware_image_source = None

  def __init__(self, manifest, work_dir, download=True, archive=True, jobs=1):
    self.manifest = manifest
    self.work_dir = work_dir
    self.download = download
    self.archive = archive
    self.jobs = jobs

  def Main(self):
    self.ProcessManifest()
    self.LocateResources()
    self.DownloadResources()
    self.PrepareProjectConfig()
    self.AddProjectToolkit()
    self.AddDefaultCompleteScript()
    self.AddFirmwareUpdaterAndImages()
    self.GetAndSetResourceVersions()
    self.PrepareNetboot()
    self.UpdateInstallShim()
    self.RemoveUnnecessaryFiles()
    self.UpdateReadme()
    self.Archive()

  def ProcessManifest(self):
    try:
      CheckDictKeys(self.manifest, [
          'board',
          'project',
          'bundle_name',
          'server_url',
          'toolkit',
          'test_image',
          'release_image',
          'firmware',
          'hwid',
          'has_firmware',
          'designs',
      ])
    except ValueError as e:
      logging.error(str(e))
      raise FinalizeBundleException(
          'Invalid manifest content. '
          'Please refer to setup/BUNDLE.md (https://goo.gl/pM1pxo)')

    self.build_board = cros_board_utils.BuildBoard(self.manifest['board'])
    self.board = self.build_board.full_name
    self.gsutil = gsutil.GSUtil(self.board)
    # assume project=board for backward compatibility
    self.project = self.manifest.get('project', self.board).lower()
    # assume designs=None for backward compatibility
    self.designs = self.manifest.get('designs', None)
    if not (self.designs == BOXSTER_DESIGNS or self.designs is None or
            isinstance(self.designs, list)):
      raise FinalizeBundleException(
          'The designs (currently %r) should be %r, None or a list of str.' %
          (self.designs, BOXSTER_DESIGNS))

    self.bundle_name = self.manifest['bundle_name']
    if not re.match(r'\d{8}_', self.bundle_name):
      raise FinalizeBundleException(
          "The bundle_name (currently %r) should be today's date, "
          'plus an underscore, plus a description of the build, e.g.: %r' %
          (self.bundle_name, time.strftime('%Y%m%d_proto')))

    # If the basename of the working directory is equal to the expected name, we
    # believe that the user intentionally wants to make the bundle in the
    # working directory (this is also needed if any of the resource is assigned
    # as local). Otherwise, we'll create a directory with expected name under
    # the working directory.
    expected_dir_name = 'factory_bundle_%s_%s' % (self.project,
                                                  self.bundle_name)
    logging.info('Expected bundle directory name is %r', expected_dir_name)
    if expected_dir_name == os.path.basename(self.work_dir):
      self.bundle_dir = self.work_dir
      logging.info('The working directory name matches the expected bundle '
                   'directory name, will finalized bundle directly in the '
                   'working directory %r', self.bundle_dir)
    else:
      self.bundle_dir = os.path.join(self.work_dir, expected_dir_name)
      logging.info('The working directory name does not match the expected '
                   'bundle directory name, will create a new directoy and '
                   'finalize bundle in %r', self.bundle_dir)
    self.bundle_dir = os.path.realpath(self.bundle_dir)
    file_utils.TryMakeDirs(self.bundle_dir)

    self.test_image_source = self.manifest.get('test_image')
    self.release_image_source = self.manifest.get('release_image')
    self.toolkit_source = self.manifest.get('toolkit')
    self.firmware_source = self.manifest.get('firmware', 'release_image')

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
    # Get the image version and remove the milestone prefix, if any.
    image_version = re.sub(r'^R\d+-', '', self._GetImageVersion(image_path))
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
        raise FinalizeBundleException(
            'Requested %s version is %r but found a local one with different '
            'version at %r' % (resource_name, resource_source, resource_path))
    elif len_found_entries > 1:
      raise FinalizeBundleException(
          'There should be only one %s in %r but found multiple: %r' % (
              resource_name, search_dirs, found_entries))
    else:
      assert len_found_entries == 0
      if is_local:
        raise FinalizeBundleException(
            '%s source is specified as %r but no one found under %r' % (
                resource_name.capitalize(), LOCAL, abs_search_dirs))
      if not self.download:
        raise FinalizeBundleException(
            'Need %s but no files found under %r' % (
                resource_name.capitalize(), abs_search_dirs))
      # Will be downloaded later.

    return resource_path

  def _LocateSignedFactoryShim(self, resource_source, search_dir):
    """Locates a signed factory shim under the search directory.

    Args:
      resource_source: source of the resource, a version string.
      search_dir: the directory under self.bundle_dir to search.

    Returns:
      Path to the resource if its version matches, otherwise returns None.
    """
    resource_name = 'signed factory shim'
    abs_search_dir = os.path.join(self.bundle_dir, search_dir)

    logging.info('Searching %s in %s', resource_name, search_dir)
    for signed_factory_shim in glob.glob(os.path.join(
        abs_search_dir, 'chromeos_*_factory*.bin')):
      pattern = 'chromeos_(.*)_{board}_factory'.format(board=self.board)
      version_match = re.search(pattern, signed_factory_shim)
      if version_match and version_match.group(1) == resource_source:
        logging.info('A local copy of %s is found at %r', resource_name,
                     signed_factory_shim)
        return signed_factory_shim

    return None

  def LocateResources(self):
    """Locates test image, release image, and factory toolkit.

    This function tries to locate test image, release image, and factory toolkit
    in self.bundle_dir, and sets the following attributes respectively:
    - self.test_image_path
    - self.releases_image_path
    - self.toolkit_path

    If a resource is found, the corresponding attribute is set to its path; if
    it's not found, the attribute is set to None (and we'll raise an error if
    the source of the resource is set to LOCAL or if self.download is set
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

    if self.toolkit_source != LOCAL:
      self.signed_shim_path = self._LocateSignedFactoryShim(
          self.toolkit_source, FACTORY_SHIM_SEARCH_DIR)


  def _CheckGSUtilVersion(self):
    # Check for gsutil >= 3.32.
    version = self.gsutil.GetVersion()
    # Remove 'pre...' string at the end, if any
    version = re.sub('pre.*', '', version)
    version_split = [int(x) for x in version.split('.')]
    if version_split < REQUIRED_GSUTIL_VERSION:
      raise FinalizeBundleException(
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
    # TODO: skip download if this is equal to self.release_image_source.
    need_firmware = self.firmware_source.startswith('release_image/')

    # TODO(crbug.com/707155): see #c1. We have to always download the factory
    #                         toolkit unless the "toolkit" source in config
    #                         refers to only the toolkit version instead of
    #                         factory.zip.
    need_toolkit = (self.toolkit_source != LOCAL)

    need_signed_shim = (self.signed_shim_path is None and
                        self.toolkit_source != LOCAL)

    if (not need_test_image and not need_release_image and not need_toolkit and
        not need_signed_shim):
      return

    # Make sure gsutil is up to date; older versions are pretty broken.
    self._CheckGSUtilVersion()

    if self.download:
      max_workers = 1 + (need_toolkit or need_signed_shim or
                         self.signed_shim_path
                        ) + need_test_image + need_release_image + need_firmware
      max_workers = min(max_workers, self.jobs)
      not_done_jobs: Set[concurrent.futures.Future] = set()
      try:
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers)
        if need_test_image:
          download_test_image = executor.submit(
              self._DownloadTestImage, self.test_image_source,
              os.path.join(self.bundle_dir, TEST_IMAGE_SEARCH_DIRS[0]))
          not_done_jobs.add(download_test_image)

        if need_release_image:
          download_release_image = executor.submit(
              self._DownloadReleaseImage, self.release_image_source,
              os.path.join(self.bundle_dir, RELEASE_IMAGE_SEARCH_DIRS[0]))
          not_done_jobs.add(download_release_image)
        else:
          download_release_image = None

        if need_toolkit:
          download_toolkit = executor.submit(self._DownloadFactoryToolkit,
                                             self.toolkit_source,
                                             self.bundle_dir)
          download_project_toolkit = executor.submit(
              self._DownloadProjectToolkit, self.toolkit_source,
              self.bundle_dir)
          not_done_jobs.add(download_toolkit)
          not_done_jobs.add(download_project_toolkit)
        else:
          download_toolkit = None
          download_project_toolkit = None

        abs_factory_shim_dir = os.path.join(self.bundle_dir,
                                            FACTORY_SHIM_SEARCH_DIR)

        if need_signed_shim or self.signed_shim_path:

          def GetInstallShim():
            if need_signed_shim:
              if download_toolkit:
                # Make sure we have downloaded the toolkit.
                download_toolkit.result()
              return self._TryDownloadSignedFactoryShim(self.toolkit_source,
                                                        abs_factory_shim_dir)
            return self.signed_shim_path

          get_install_shim = executor.submit(GetInstallShim)
          not_done_jobs.add(get_install_shim)

        if need_firmware:
          firmware_source_version = self.firmware_source.split('/')[1]
          if firmware_source_version != self.release_image_source:
            download_firmware_image = executor.submit(
                self._DownloadReleaseImage, firmware_source_version,
                os.path.join(self.bundle_dir, FIRMWARE_IMAGE_SOURCE_DIR))
            not_done_jobs.add(download_firmware_image)
          elif download_release_image:
            download_firmware_image = download_release_image
          else:
            download_firmware_image = None
            self.firmware_image_source = self.release_image_path
        # This loop raises an exception if any job raises an exception or
        # there is a keyboard interrupt.
        while not_done_jobs:
          done_jobs, not_done_jobs = concurrent.futures.wait(
              not_done_jobs, return_when=concurrent.futures.FIRST_EXCEPTION)
          for done_job in done_jobs:
            if done_job.exception():
              raise done_job.exception()
        # All jobs should be done.
        if need_test_image:
          self.test_image_path = download_test_image.result()
        if need_release_image:
          self.release_image_path = download_release_image.result()
        if need_toolkit:
          self.toolkit_path = download_toolkit.result()
        if need_signed_shim or self.signed_shim_path:
          self.signed_shim_path = get_install_shim.result()
          if self.signed_shim_path:
            # Remove the unsigned factory shim if the signed factory shim
            # exists.
            file_utils.TryUnlink(
                os.path.join(abs_factory_shim_dir, 'factory_install_shim.bin'))
        if need_firmware and download_firmware_image:
          self.firmware_image_source = download_firmware_image.result()
      finally:
        # Cancel all not done jobs if there is an exception.
        for job in not_done_jobs:
          job.cancel()
        executor.shutdown(wait=True)
      if (not self.test_image_path or not os.path.exists(self.test_image_path)):
        raise FinalizeBundleException(
            'No test image at %s' % self.test_image_path)
      if (not self.release_image_path or
          not os.path.exists(self.release_image_path)):
        raise FinalizeBundleException(
            'No release image at %s' % self.release_image_path)
      if (need_firmware and (not self.firmware_image_source or
                             not os.path.exists(self.firmware_image_source))):
        raise FinalizeBundleException(
            'No release image for firmware at %s' % self.firmware_image_source)

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

  def AddProjectToolkit(self):
    """Use project toolkit if exists and the source is not local."""
    if self.toolkit_source == LOCAL:
      return
    package = os.path.join(self.bundle_dir, PROJECT_TOOLKIT_PACKAGES)
    extracted_dir = os.path.join(self.bundle_dir, 'factory_project_toolkits')
    if os.path.exists(package):
      file_utils.ExtractFile(package, extracted_dir)
      os.remove(package)
    project_toolkit_path = os.path.join(
        extracted_dir, f'{self.project}_install_factory_toolkit.run')
    if os.path.exists(project_toolkit_path):
      logging.info('Moving %r to %r', project_toolkit_path, self.toolkit_path)
      shutil.move(project_toolkit_path, self.toolkit_path)

  def AddDefaultCompleteScript(self):
    """Adds default complete script if not set."""
    complete_dir = os.path.join(self.bundle_dir, 'complete')
    file_utils.TryMakeDirs(complete_dir)
    num_complete_scripts = len(os.listdir(complete_dir))

    if num_complete_scripts == 1:
      # Complete script already provided.
      return
    if num_complete_scripts > 1:
      raise FinalizeBundleException(
          'Not having exactly one file under %s.' % complete_dir)

    default_complete_script = os.path.join(
        self.bundle_dir, 'setup', 'complete_script_sample.sh')
    shutil.copy(default_complete_script, complete_dir)

  def AddFirmwareUpdaterAndImages(self):
    """Add firmware updater into bundle directory, and extract firmware images
    into firmware_images/."""

    firmware_src = self.manifest.get('firmware', 'release_image')
    firmware_dir = os.path.join(self.bundle_dir, FIRMWARE_SEARCH_DIR)
    file_utils.TryMakeDirs(firmware_dir)
    if firmware_src.startswith('release_image'):
      with MountPartition(self.release_image_path, 3) as f:
        shutil.copy(os.path.join(f, FIRMWARE_UPDATER_PATH), firmware_dir)
    elif firmware_src.startswith('release_image/'):
      with MountPartition(self.firmware_image_source, 3) as f:
        shutil.copy(os.path.join(f, FIRMWARE_UPDATER_PATH), firmware_dir)
    elif firmware_src != LOCAL:
      # TODO: check input in ProcessManifest(), not here.
      raise FinalizeBundleException(
          'firmware must be either "release_image", '
          'release_image/{version}" or "%s".' % LOCAL)

    updaters = os.listdir(firmware_dir)
    if len(updaters) != 1:
      raise FinalizeBundleException(
          'Not having exactly one file under %s.' % firmware_dir)
    updater_path = os.path.join(firmware_dir, updaters[0])

    firmware_images_dir = os.path.join(self.bundle_dir, 'firmware_images')
    file_utils.TryMakeDirs(firmware_images_dir)

    with file_utils.TempDirectory() as temp_dir:
      process = Spawn(['sh', updater_path, '--unpack', temp_dir], log=True,
                      call=True)
      # TODO(cyueh) Remove sb_extract after we dropping support for legacy
      # firmware updater.
      if process.returncode != 0:
        Spawn(['sh', updater_path, '--sb_extract', temp_dir], log=True,
              check_call=True)

      for root, unused_dirs, files in os.walk(temp_dir):
        for filename in files:
          if filename.endswith('.bin'):
            shutil.copy(os.path.join(root, filename),
                        firmware_images_dir)

      # Collect only the desired firmware
      if self.designs is not None:
        manifest = json_utils.LoadFile(os.path.join(temp_dir, 'manifest.json'))
        keep_list = set()
        for design in manifest:
          if design in self.designs:
            keep_list.add(manifest[design].get('host', {}).get('image'))
            keep_list.add(manifest[design].get('ec', {}).get('image'))
          else:
            Spawn(['rm', '-rf',
                   os.path.join(temp_dir, 'models', design)], log=True,
                  check_call=True)
        for f in os.listdir(os.path.join(temp_dir, 'images')):
          if os.path.join('images', f) not in keep_list:
            os.remove(os.path.join(temp_dir, 'images', f))
        process = Spawn(['sh', updater_path, '--repack', temp_dir], log=True,
                        call=True)
        # TODO(cyueh) Remove sb_repack after we dropping support for legacy
        # firmware updater.
        if process.returncode != 0:
          Spawn(['sh', updater_path, '--sb_repack', temp_dir], log=True,
                check_call=True)

    # Try to use "chromeos-firmwareupdate --mode=output" to extract bios/ec
    # firmware. This option is available for updaters extracted from image
    # version >= 9962.0.0. This also checks that the firmwares that we care
    # exist.
    models = [self.project] if self.designs is None else self.designs
    for model in models:
      Spawn([
          'sudo', 'sh', updater_path, '--mode', 'output', '--model', model,
          '--output_dir', firmware_images_dir
      ], log=True, call=True)

  def PrepareNetboot(self):
    """Prepares netboot resource for TFTP setup."""
    # TODO(hungte) Change factory_shim/netboot/ to be netboot/ in factory.zip.
    orig_netboot_dir = os.path.join(self.bundle_dir, 'factory_shim', 'netboot')
    netboot_dir = os.path.join(self.bundle_dir, 'netboot')
    netboot_backup_dir = os.path.join(self.bundle_dir, 'netboot_backup')
    # Overwrite netboot_dir if we download bundle_dir again and orig_netboot_dir
    # appears again.
    if os.path.exists(orig_netboot_dir):
      if os.path.exists(netboot_dir):
        shutil.rmtree(netboot_dir)
      if os.path.exists(netboot_backup_dir):
        shutil.rmtree(netboot_backup_dir)
      shutil.move(orig_netboot_dir, netboot_dir)
    elif os.path.exists(netboot_backup_dir):
      for f in glob.glob(os.path.join(netboot_backup_dir, '*')):
        shutil.move(f, netboot_dir)

    if not os.path.exists(netboot_dir):
      logging.info('No netboot resources.')
      return

    # Try same convention that sys-boot/chromeos-bootimage is doing:
    # bootfile=${PORTAGE_USERNAME}/${BOARD_USE}/vmlinuz
    # argfile=${PORTAGE_USERNAME}/${BOARD_USE}/cmdline
    files_dir = os.path.join('chrome-bot', self.board)
    target_bootfile = os.path.join(files_dir, 'vmlinuz')
    target_argsfile = os.path.join(files_dir, 'cmdline')

    server_url = self.manifest.get('server_url')
    tftp_server_ip = (urllib.parse.urlparse(server_url).hostname if server_url
                      else '')

    netboot_firmware_images = set(
        glob.glob(os.path.join(netboot_dir, 'image*.net.bin')))
    useful_images = netboot_firmware_images
    if self.designs is not None:
      useful_images = useful_images & set(
          [os.path.join(netboot_dir, 'image.net.bin')] + [
              os.path.join(netboot_dir, 'image-%s.net.bin' % design)
              for design in self.designs
          ])
    not_useful_images = netboot_firmware_images - useful_images
    if not_useful_images:
      file_utils.TryMakeDirs(netboot_backup_dir)
      for netboot_firmware_image in not_useful_images:
        shutil.move(netboot_firmware_image, netboot_backup_dir)

    def SetOneNetbootImage(netboot_firmware_image):
      new_netboot_firmware_image = netboot_firmware_image + '.INPROGRESS'
      args = ['--argsfile', target_argsfile,
              '--bootfile', target_bootfile,
              '--input', netboot_firmware_image,
              '--output', new_netboot_firmware_image]
      if server_url:
        args += ['--factory-server-url=%s' % server_url,
                 '--tftpserverip=%s' % tftp_server_ip]
      Spawn(_GetImageTool() + ['netboot'] + args, check_call=True, log=True)
      shutil.move(new_netboot_firmware_image, netboot_firmware_image)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=self.jobs) as executor:
      executor.map(SetOneNetbootImage, useful_images)

    tftp_root = os.path.join(self.bundle_dir, 'netboot', 'tftp')
    tftp_board_dir = os.path.join(tftp_root, files_dir)
    file_utils.TryMakeDirs(tftp_board_dir)

    # omaha_conf is fetched by factory_installer explicitly.
    if server_url:
      # TODO(hungte) Rename omahaserver_* to factory_server_*.conf.
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
          raise FinalizeBundleException(
              'Unable to set factory server URL in %s' % lsb_factory_path)

      if lsb_factory == orig_lsb_factory:
        return False  # No changes
      file_utils.WriteWithSudo(lsb_factory_path, lsb_factory)
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
      raise FinalizeBundleException(
          'Both unsigned and signed install shim exists. '
          'Please remove unsigned one')
    if len(signed_shims) > 1:
      raise FinalizeBundleException(
          'Expected to find 1 signed factory shim but found %d: %r' % (
              len(signed_shims), signed_shims))
    if len(signed_shims) == 1:
      PatchInstallShim(signed_shims[0])
      has_install_shim = True

    if not has_install_shim:
      logging.warning('There is no install shim in the bundle.')

  def PrepareProjectConfig(self):
    config_dir = os.path.join(self.bundle_dir, 'project_config')
    if not os.path.exists(config_dir):
      logging.warning('There is no %r in the bundle.', config_dir)
      if self.designs == BOXSTER_DESIGNS:
        self.designs = None
      return

    extracted_dir = os.path.join(config_dir, 'extracted')
    file_utils.TryMakeDirs(extracted_dir)

    config_balls = sorted(glob.glob(os.path.join(config_dir, '*.tar.gz')))
    for config_ball in config_balls:
      Spawn(['tar', '-xf', config_ball, '-C', extracted_dir],
            check_call=True, log=True)
      os.remove(config_ball)

    config = '%s_%s_model_sku.json' % (self.board, self.project)
    config_path = os.path.join(extracted_dir, config)

    if not os.path.exists(config_path):
      logging.warning('There is no %r in the project_config.', config)
      if self.designs == BOXSTER_DESIGNS:
        self.designs = None
      return

    if self.designs == BOXSTER_DESIGNS:
      model_sku = json_utils.LoadFile(config_path)
      self.designs = list(model_sku['model'])

    Spawn(['tar', '-zcf', os.path.join(config_dir, 'project_config.tar.gz'),
           '-C', extracted_dir, config], check_call=True, log=True)
    os.remove(config_path)

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
    REQUIRED_SECTIONS = ['VITAL INFORMATION', 'CHANGES']

    # Grok the README file; we'll be modifying it.
    try:
      readme_sections = re.findall(
          # Section header
          r'\*\*\*\n\*\n\* (.+?)\n\*\n\*\*\*\n'
          # Anything up to (but not including) the next section header
          r'((?:(?!\*\*\*).)+)',
          file_utils.ReadFile(self.readme_path), re.DOTALL)
      # This results in a list of tuples (x, y), where x is the name of the
      # section, and y is the contents of the section. Turn each tuple into a
      # list; we'll be modifying some of them.
      readme_sections = [list(s) for s in readme_sections]
    except Exception:
      readme_sections = [[x, '\n'] for x in REQUIRED_SECTIONS]

    readme_section_index = {}  # Map of section name to index
    for i, s in enumerate(readme_sections):
      readme_section_index[s[0]] = i
    for x in REQUIRED_SECTIONS:
      if x not in readme_section_index:
        raise FinalizeBundleException('README is missing %s section' % x)

    # Make sure that the CHANGES section contains this version.
    expected_str = '%s changes:' % self.bundle_name
    if expected_str not in readme_sections[readme_section_index['CHANGES']][1]:
      logging.warning('The string %r was not found in the CHANGES section. '
                      'Please add a section for it (if this is the first '
                      'version, just say "initial release").', expected_str)

    def _ExtractFirmwareVersions(updater_file, updater_name):
      firmware_versions = _GetFirmwareVersions(updater_file, self.has_firmware)
      return [('%s %s' % (updater_name, firmware_type), version)
              for firmware_type, version in firmware_versions.items()
              if version is not None]

    # Get some vital information
    vitals = [('Board', self.board), ('Project', self.project)]
    if self.designs is not None:
      vitals.append(('Designs', repr(self.designs)))
    vitals.append(
        ('Bundle',
         '%s (created by %s, %s)' % (self.bundle_name, os.environ['USER'],
                                     time.strftime('%a %Y-%m-%d %H:%M:%S %z'))))
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
              stateful_total_bytes // 1024 // 1024,
              stateful_free_bytes // 1024 // 1024,
              stateful_free_bytes * 100 // stateful_total_bytes)))
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
        elif f in ['ec.bin', 'bios.bin', 'image.bin'] or re.match(
            r'^image.*\.net\.bin$', f):
          version = get_version.GetFirmwareBinaryVersion(path)
          if not version:
            raise FinalizeBundleException(
                'Unable to find firmware version in %s' % path)
          vitals.append((relpath, version))

    vital_lines = []
    max_key_length = max(len(k) for k, v in vitals)
    for k, v in vitals:
      vital_lines.append('%s:%s %s' % (k, ' ' * (max_key_length - len(k)), v))
    vital_contents = '\n'.join(vital_lines)
    readme_sections[readme_section_index['VITAL INFORMATION']][1] = (
        vital_contents + '\n\n')

    with open(self.readme_path, 'w') as f:
      for section in readme_sections:
        f.write('***\n'
                '*\n'
                '* %s\n'
                '*\n'
                '***\n'
                '%s' % tuple(section))
    logging.info('\n\nUpdated %s; vital information:\n%s\n',
                 self.readme_path, vital_contents)

  def Archive(self):
    if self.archive:
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

      image_tool_output_file = os.path.join(
          self.work_dir, 'factory_bundle_%s_%s.tar.bz2' % (self.board,
                                                           self.bundle_name))
      output_file = os.path.join(
          self.work_dir, 'factory_bundle_%s_%s.tar.bz2' % (self.project,
                                                           self.bundle_name))
      args = ['bundle', '-o', self.work_dir, '--board', self.board,
              '--timestamp', self.bundle_name.split('_')[0],
              '--phase', self.bundle_name.split('_')[1]]
      args += ['--project', self.project]
      if self.designs:
        args += ['--designs']
        args += self.designs
      if self.signed_shim_path:
        args += ['--factory_shim', self.signed_shim_path]
      Spawn(_GetImageTool() + args,
            log=True, check_call=True, cwd=self.bundle_dir)
      if image_tool_output_file != output_file:
        Spawn(['mv', image_tool_output_file, output_file],
              log=True, check_call=True)
      logging.info(
          'Created %s (%.1f GiB).',
          output_file, os.path.getsize(output_file) / (1024 * 1024 * 1024))

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
  def _DownloadResource(self, possible_urls, resource_name=None, version=None):
    """Downloads a resource file from given URLs.

    This function downloads a resource from a list of possible URLs (only the
    first one found by the function will be downloaded). If no file is found at
    all possible URLs, an exception will be raised.

    Args:
      possible_urls: a single or a list of possible GS URLs to search.
      resource_name: a human readable name of the resource, just for logging,
          won't affect the behavior of downloading.
      version: version of the resource, just for logging.
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
      raise FinalizeBundleException(
          'No %s found for version %s' % (resource_name, version))
    logging.info('Starting to download %s...', found_url)
    downloaded_path = self.gsutil.GSDownload(found_url)

    try:
      yield (downloaded_path, found_url)
    finally:
      file_utils.TryUnlink(downloaded_path)

  def _DownloadAndExtractImage(self, image_name, version, possible_urls,
                               target_dir):
    with self._DownloadResource(
        possible_urls, image_name, version) as (downloaded_path, found_url):
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
        file_utils.TryUnlink(downloaded_path)

  def _DownloadTestImage(self, requested_version, target_dir):
    possible_urls = []
    for channel in RESOURCE_CHANNELS:
      url = '%s/%s' % (
          gsutil.BuildResourceBaseURL(
              channel, self.build_board.gsutil_name, requested_version),
          '*test*.tar.xz')
      possible_urls.append(url)
    return self._DownloadAndExtractImage('test image', requested_version,
                                         possible_urls, target_dir)

  def _DownloadReleaseImage(self, requested_version, target_dir):
    possible_urls = []
    # Signed recovery image ends with .bin and takes higher priority, so .bin
    # must be searched first. Unsigned recovery image ends with .tar.xz.
    for ext in ['.bin', '.tar.xz']:
      for channel in RESOURCE_CHANNELS:
        url = '%s/%s%s' % (
            gsutil.BuildResourceBaseURL(
                channel, self.build_board.gsutil_name, requested_version),
            '*recovery*', ext)
        possible_urls.append(url)
    return self._DownloadAndExtractImage('release image', requested_version,
                                         possible_urls, target_dir)

  def _DownloadFactoryToolkit(self, requested_version, target_dir):
    """Downloads factory_image.zip.

    For older builds, the archive has different name so the pattern is
    '*factory*.zip'.

    Returns:
      The path of toolkit directory.
    """
    possible_urls = []
    for channel in RESOURCE_CHANNELS:
      url = '%s/%s' % (
          gsutil.BuildResourceBaseURL(
              channel, self.build_board.gsutil_name, requested_version),
          '*factory*.zip')
      possible_urls.append(url)
    with self._DownloadResource(
        possible_urls, 'factory toolkit', requested_version
    ) as (downloaded_path, unused_url):
      file_utils.ExtractFile(downloaded_path, target_dir, exclude=['*/README'])

    return self._LocateOneResource(
        'factory toolkit', LOCAL, TOOLKIT_SEARCH_DIRS,
        lambda unused_path, unused_version: True)

  def _DownloadProjectToolkit(self, requested_version, target_dir):
    """Downloads PROJECT_TOOLKIT_PACKAGES.

    Returns:
      The path of the package or None if the package is absent.
    """
    if not self.designs:
      return None
    branches = ['factory', 'release']
    possible_urls = [
        'gs://chromeos-image-archive/%s-%s/R*-%s/%s' %
        (self.build_board.gsutil_name, branch, requested_version,
         PROJECT_TOOLKIT_PACKAGES) for branch in branches
    ]
    try:
      with self._DownloadResource(
          possible_urls, 'project specific toolkit',
          requested_version) as (downloaded_path, found_url):
        dst_path = os.path.join(target_dir, os.path.basename(found_url))
        logging.info('Moving %r to %r', downloaded_path, dst_path)
        file_utils.TryMakeDirs(target_dir)
        shutil.move(downloaded_path, dst_path)
      return dst_path
    except FinalizeBundleException as e:
      # The project specific toolkit isn't found.
      logging.info(e)

    return None

  def _TryDownloadSignedFactoryShim(self, requested_version, target_dir):
    possible_urls = []
    for channel in RESOURCE_CHANNELS:
      url = '%s/%s' % (
          gsutil.BuildResourceBaseURL(
              channel, self.build_board.gsutil_name, requested_version),
          'chromeos_*_factory*.bin')
      possible_urls.append(url)
    try:
      with self._DownloadResource(
          possible_urls, 'signed factory shim', requested_version
      ) as (downloaded_path, found_url):
        shim_basename = os.path.basename(found_url)
        dst_path = os.path.join(target_dir, shim_basename)
        logging.info('Moving %r to %r', downloaded_path, dst_path)
        file_utils.TryMakeDirs(target_dir)
        shutil.move(downloaded_path, dst_path)
    except FinalizeBundleException as e:
      # If the signed factory shim isn't found, there is still an unsigned
      # factory shim extracted from the factory.zip.  So ignore this exception
      # here.
      logging.info(e)

    return self._LocateSignedFactoryShim(
        requested_version, FACTORY_SHIM_SEARCH_DIR)

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

  @staticmethod
  def FromArgs():
    args = FinalizeBundle._ParseArgs()
    if os.path.isdir(args.manifest):
      manifest_path = os.path.join(args.manifest, 'MANIFEST.yaml')
    else:
      manifest_path = args.manifest
    try:
      manifest = yaml.load(file_utils.ReadFile(manifest_path))
    except Exception:
      logging.exception('Failed to load manifest: %s', manifest_path)
      logging.error('Please refer to setup/BUNDLE.md (https://goo.gl/pM1pxo)')
      raise
    work_dir = args.dir or os.path.dirname(os.path.realpath(manifest_path))
    return FinalizeBundle(manifest, work_dir, args.download, args.archive,
                          args.jobs)

  @staticmethod
  def _ParseArgs():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=USAGE)

    parser.add_argument(
        '--no-download', dest='download', action='store_false',
        help="Don't download files from Google Storage (for testing only)")
    parser.add_argument(
        '--no-archive', dest='archive', action='store_false',
        help="Don't make a tarball (for testing only)")
    parser.add_argument('--jobs', dest='jobs', type=int, default=1,
                        help='How many workers to work at maximum.')

    parser.add_argument('manifest', metavar='MANIFEST',
                        help=(
                            'Path to the manifest file or the directory '
                            'containing MANIFEST.yaml'))
    parser.add_argument('dir', metavar='DIR', nargs='?',
                        default=None, help='Working directory')

    args = parser.parse_args()
    assert args.jobs > 0
    return args


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  try:
    FinalizeBundle.FromArgs().Main()
  except Exception:
    logging.exception('')
    sys.exit(1)
