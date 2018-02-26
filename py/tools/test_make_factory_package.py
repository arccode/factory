#!/usr/bin/env python

# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Regression test for make_factory_package.sh.

This is run manually on the command line (use -h for command-line usage).
"""


import argparse
import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountPartition


DESCRIPTION = r"""Tests make_factory_package.sh with real build artifacts.

The first argument (mandatory) is the URL to a directory containing
build artifacts. The necessary artifacts are copied to local storage
and unpacked, and make_factory_packages.sh (from the local source
tree, not from the build artifacts) is run several times and the
results tested.

For example:

  py/tools/test_make_factory_package.py --artifacts \
      gs://chromeos-image-archive/daisy-release/R37-5978.7.0

For developers without access to release repositories, public artifact
directories may also be used, with the --no-release flag:

  py/tools/test_make_factory_package.py --no-release --artifacts \
      gs://chromeos-image-archive/x86-generic-full/R38-5991.0.0-b13993
"""


def PrepareArtifacts(url):
  """Downloads and unpacks artifacts necessary to run make_factory_package.sh.

  The artifacts are stored in a temporary directory, and the name of
  the directory is returned. The directory name is based on a hash of
  the URL so this script can be run multiple times without needing to
  re-download the artifacts each time.
  """
  # pylint: disable=no-member
  artifacts_dir = (
      os.path.join(
          tempfile.gettempdir(),
          'test_make_factory_package.artifacts.%s' % hashlib.md5(url).
          hexdigest()[0:16]))

  setup_complete_path = os.path.join(artifacts_dir, 'SETUP_COMPLETE')
  if os.path.exists(os.path.join(artifacts_dir, setup_complete_path)):
    logging.info('%s has already been downloaded and setup into %s; '
                 'reusing it', url, artifacts_dir)
    # Already setup
    return artifacts_dir

  patterns = ('factory_image.zip',
              'chromiumos_base_image.tar.xz',
              'chromiumos_test_image.tar.xz')

  if os.path.exists(artifacts_dir):
    shutil.rmtree(artifacts_dir)
  os.makedirs(artifacts_dir)

  # Save the URL we downloaded everything from. This isn't used for
  # anything, but it's useful documentation in case someone looks at
  # the directory.
  file_utils.WriteFile(os.path.join(artifacts_dir, 'URL'), url)

  unpacked_path = os.path.join(artifacts_dir, 'unpacked')
  os.mkdir(unpacked_path)

  logging.info('Setting up artifacts from %s into %s', url, artifacts_dir)
  for pattern in patterns:
    Spawn(['gsutil', 'cp', os.path.join(url, pattern), artifacts_dir],
          check_call=True)
    archive_path = file_utils.GlobSingleFile(
        os.path.join(artifacts_dir, pattern))
    file_utils.ExtractFile(archive_path, unpacked_path)

  logging.info('Setup complete: touching %s', setup_complete_path)
  file_utils.TouchFile(setup_complete_path)

  return artifacts_dir


class MakeFactoryPackageTest(unittest.TestCase):
  # To be set by main()
  artifacts_dir = None
  args = None

  def setUp(self):
    self.tmp_dir = (self.args.tmp_dir or
                    tempfile.mkdtemp(prefix='test_make_factory_package.'))
    self.make_factory_package = os.path.join(
        paths.FACTORY_DIR, 'setup', 'make_factory_package.sh')
    self.hwid = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'testdata', 'hwid_v3_bundle_X86-GENERIC.sh')
    self.firmware_updater = os.path.join(self.tmp_dir,
                                         'chromeos-firmwareupdate')
    file_utils.WriteFile(self.firmware_updater, 'dummy firmware updater')

    self.base_args = [
        self.make_factory_package,
        '--toolkit', 'unpacked/toolkit/install_factory_toolkit.run',
        '--test', 'unpacked/chromiumos_test_image.bin',
        '--release', 'unpacked/chromiumos_base_image.bin',
        '--hwid', self.hwid,
    ]

  def tearDown(self):
    if not self.args.save_tmp:
      shutil.rmtree(self.tmp_dir)

  def testUSBImg(self):
    image = os.path.join(self.tmp_dir, 'out.img')
    if not self.args.skip_mfp:
      Spawn(self.base_args + [
          '--usbimg', image,
          '--firmware', self.firmware_updater,
          '--factory_shim',
          'unpacked/factory_shim/factory_install_shim.bin',
      ],
            cwd=self.artifacts_dir, check_call=True, log=True)

    self.CheckPartitions(self.PartitionMapForImage(image, 2), True)

  def testDiskImg(self):
    image = os.path.join(self.tmp_dir, 'out.img')
    if not self.args.skip_mfp:
      Spawn(self.base_args + ['--diskimg', image],
            cwd=self.artifacts_dir, check_call=True, log=True)

    self.CheckPartitions(self.PartitionMapForImage(image), True)

  def CheckPartitions(self, partition_map, expect_hwid):
    """Checks that partitions are set up correctly.

    Args:
      partition_map: A dict where each entry maps a partition name (one
          of 'state', 'rootfs-release', or 'rootfs-test') to a dict of
          MountPartition arguments that can be used to mount the
          partition (e.g., dict(source_path='/tmp/foo', index=2) to mount the
          second partition in the file /tmp/foo).
      expect_hwid: Whether we expect to find the HWID file in the stateful
          partition at dev_image/factory/hwid/X86-GENERIC.
    """
    # Check that rootfs-test and rootfs-release are mountable and that
    # lsb-release is correct.  rootfs-test should have
    # "testimage-channel" as the release track, and rootfs-release
    # should not.
    for partition in ('rootfs-test', 'rootfs-release'):
      with MountPartition(**partition_map[partition]) as path:
        lsb_release = file_utils.ReadFile(
            os.path.join(path, 'etc', 'lsb-release'))
        is_test_image = ('CHROMEOS_RELEASE_TRACK=testimage-channel' in
                         lsb_release.splitlines())
        self.assertEquals(partition == 'rootfs-test', is_test_image)

    # Stateful partition checks.
    with MountPartition(**partition_map['state']) as stateful:
      # Check for the HWID file (if we expect to find one).
      hwid_file = os.path.join(stateful, 'dev_image', 'factory',
                               'hwid', 'X86-GENERIC')
      self.assertEquals(expect_hwid, os.path.exists(hwid_file))
      if expect_hwid:
        search_result = re.search(
            '^(board|project):', file_utils.ReadFile(hwid_file), re.MULTILINE)
        assert search_result, (
            '%s should be a valid HWID file, but it does not contain a '
            'line beginning with "board:" or "project:"' % hwid_file)

      # For release builds, there should be a stateful_files.tar.xz
      # archive in the generated stateful partition.
      stateful_files_tar = os.path.join(stateful, 'stateful_files.tar.xz')
      if self.args.release:
        self.assertTrue(os.path.exists(stateful_files_tar))
        stateful_files_unpacked = os.path.join(self.tmp_dir, 'stateful_files')
        file_utils.TryMakeDirs(stateful_files_unpacked)
        file_utils.ExtractFile(stateful_files_tar, stateful_files_unpacked,
                               quiet=True)
        # There should be an "unencrypted" directory.
        self.assertTrue(os.path.isdir(os.path.join(
            stateful_files_unpacked, 'unencrypted')))

  def PartitionMapForImage(self, image, offset=0):
    """Returns a partition map for a given image.

    This can be passed as the partition_map argument to CheckPartitions.

    Args:
      offset: The number of partitions by which the release and factory
          rootfs are offset.  This is 2 in USB install shims, since
          partitions #2 and #3 are used for the install shim kernel/rootfs
          (see FACTORY_INSTALL_USB_OFFSET=2 in make_factory_package.sh)
          and 0 for regular disk images.
    """
    partitions = device_utils.CreateDUTInterface().partitions
    return {'state': dict(
        source_path=image,
        index=partitions.STATEFUL.index),
            'rootfs-release': dict(
                source_path=image,
                index=partitions.RELEASE_ROOTFS.index + offset),
            'rootfs-test': dict(
                source_path=image,
                index=partitions.FACTORY_ROOTFS.index + offset)}


def main():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--artifacts', metavar='URL',
      help='URL of a directory containing build artifacts',
      default='gs://chromeos-image-archive/eve-release/R60-9578.0.0/')
  parser.add_argument(
      '--no-release', action='store_false', dest='release',
      help=('Specify if not using release artifacts '
            '(which are missing the CRX cache)'))
  parser.add_argument(
      '--save-tmp', action='store_true',
      help='Save temporary directory')
  # Hidden argument to specify a particular temporary directory
  # (implies --save-tmp)
  parser.add_argument('--tmp-dir', help=argparse.SUPPRESS)
  # Hidden argument to skip running make_factory_packages.  This is
  # useful with --tmp-dir to save time iterating on tests.
  parser.add_argument('--skip-mfp', action='store_true', help=argparse.SUPPRESS)
  parser.add_argument(
      'unittest_args', metavar='UNITTEST_ARGS',
      nargs=argparse.REMAINDER,
      help=('Arguments to pass on to unittest.main (e.g., '
            'names of tests to run'))
  args = parser.parse_args()
  args.artifacts = args.artifacts.rstrip('/')
  logging.basicConfig(level=logging.INFO)

  MakeFactoryPackageTest.artifacts_dir = PrepareArtifacts(args.artifacts)
  MakeFactoryPackageTest.args = args

  if args.tmp_dir:
    args.save_tmp = True

  logging.info('Running tests...')
  # Run tests with unittest.main
  program = unittest.main(argv=(sys.argv[0:1] + args.unittest_args), exit=False)
  if program.result.wasSuccessful() and not args.skip_mfp:
    # Touch a file to remember that the test passed; we'll check this
    # in a presubmit test
    open(os.path.join(os.path.dirname(__file__),
                      '.test_make_factory_package.passed'), 'w').close()
  sys.exit(not program.result.wasSuccessful())


if __name__ == '__main__':
  main()
