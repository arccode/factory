#!/usr/bin/env python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
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

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


DESCRIPTION = r"""Tests make_factory_package.sh with real build artifacts.

The first argument (mandatory) is the URL to a directory containing
build artifacts. The necessary artifacts are copied to local storage
and unpacked, and make_factory_packages.sh (from the local source
tree, not from the build artifacts) is run several times and the
results tested.

For example:

  py/tools/test_make_factory_package.py --artifacts \
      gs://chromeos-image-archive/x86-generic-full/R38-5991.0.0-b13993

or to run only the testMiniOmaha test:

  py/tools/test_make_factory_package.py --artifacts \
      gs://chromeos-image-archive/x86-generic-full/R38-5991.0.0-b13993 \
      MakeFactoryPackageTest.testMiniOmaha
"""


def PrepareArtifacts(url):
  """Downloads and unpacks artifacts necessary to run make_factory_package.sh.

  The artifacts are stored in a temporary directory, and the name of
  the directory is returned. The directory name is based on a hash of
  the URL so this script can be run multiple times without needing to
  re-download the artifacts each time.
  """
  # pylint: disable=E1101
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
  save_tmp = None

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp(prefix='test_make_factory_package.')
    self.make_factory_package = os.path.join(
        factory.FACTORY_PATH, 'setup', 'make_factory_package.sh')
    self.hwid = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'testdata', 'hwid_v3_bundle_X86-GENERIC.sh')
    firmware_updater = os.path.join(self.tmpdir, 'chromeos-firmwareupdate')
    file_utils.WriteFile(firmware_updater, 'dummy firmware updater')

    self.base_args = [
      self.make_factory_package,
      '--factory_toolkit',
      'unpacked/factory_toolkit/install_factory_toolkit.run',
      '--test', 'unpacked/chromiumos_test_image.bin',
      '--release', 'unpacked/chromiumos_base_image.bin',
      '--hwid_updater', self.hwid,
      '--firmware_updater', firmware_updater,
      ]

  def tearDown(self):
    if not self.save_tmp:
      shutil.rmtree(self.tmpdir)

  def testMiniOmaha(self):
    static = os.path.join(self.tmpdir, 'static')
    Spawn(self.base_args + ['--omaha_data_dir', static],
          cwd=self.artifacts_dir, check_call=True, log=True)

    # The static directory should have been created with a particular
    # set of files.
    self.assertItemsEqual(
      ['efi.gz', 'firmware.gz', 'hwid.gz', 'miniomaha.conf',
       'oem.gz', 'rootfs-release.gz', 'rootfs-test.gz', 'state.gz'],
      os.listdir(static))

    # miniomaha.conf should be parseable Python that sets the 'config'
    # variable.
    miniomaha_conf = {}
    execfile(os.path.join(static, 'miniomaha.conf'), miniomaha_conf)
    config = miniomaha_conf['config']
    self.assertItemsEqual([
        'efipartitionimg_checksum', 'efipartitionimg_image', 'factory_checksum',
        'factory_image', 'firmware_checksum', 'firmware_image', 'hwid_checksum',
        'hwid_image', 'oempartitionimg_checksum', 'oempartitionimg_image',
        'qual_ids', 'release_checksum', 'release_image', 'stateimg_checksum',
        'stateimg_image'], config[0].keys())

  def testUSBImg(self):
    image = os.path.join(self.tmpdir, 'out.img')
    Spawn(self.base_args + [
              '--usbimg', image,
              '--install_shim',
              'unpacked/factory_shim/factory_install_shim.bin',
          ],
          cwd=self.artifacts_dir, check_call=True, log=True)

    # There should be a single valid HWID file in the dev_image/factory/hwid
    # directory.
    with MountPartition(image, 1) as stateful:
      try:
        hwid_file = file_utils.GlobSingleFile(
          os.path.join(stateful, 'dev_image', 'factory', 'hwid', '*'))
      except ValueError:
        logging.error('No HWID file was saved into the USB image')
        raise

      logging.info('HWID file: %s', hwid_file)
      assert re.search('^board:', file_utils.ReadFile(hwid_file),
                       re.MULTILINE), (
          '%s should be a valid HWID file, but it does not contain a line '
          'beginning with "board:"' % hwid_file)


def main():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--save-tmp', action='store_true',
      help='Save temporary directory')
  parser.add_argument(
      '--artifacts', metavar='URL',
      help='URL of a directory containing build artifacts',
      default=('gs://chromeos-image-archive/x86-generic-full/'
               'R38-5991.0.0-b13993'))
  parser.add_argument(
      'unittest_args', metavar='UNITTEST_ARGS',
      nargs=argparse.REMAINDER,
      help=('Arguments to pass on to unittest.main (e.g., '
            'names of tests to run'))
  args = parser.parse_args()
  args.artifacts = args.artifacts.rstrip('/')
  logging.basicConfig(level=logging.INFO)

  MakeFactoryPackageTest.artifacts_dir = PrepareArtifacts(args.artifacts)
  MakeFactoryPackageTest.save_tmp = args.save_tmp

  logging.info('Running tests...')
  # Run tests with unittest.main
  program = unittest.main(argv=(sys.argv[0:1] + args.unittest_args), exit=False)
  if program.result.wasSuccessful():
    # Touch a file to remember that the test passed; we'll check this
    # in a presubmit test
    open(os.path.join(os.path.dirname(__file__),
                      '.test_make_factory_package.passed'), 'w').close()
  sys.exit(not program.result.wasSuccessful())


if __name__ == '__main__':
  main()
