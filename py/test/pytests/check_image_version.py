# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Check release or test OS image version on internal storage.

Description
-----------
This test checks if Chrome OS test image or release image version in
'/etc/lsb-release' are greater than or equal to the value of argument
``min_version``. If the version is too old and argument ``reimage`` is set to
True, download and apply either remote netboot firmware or cros_payload
components from factory server.

Note when use_netboot is specified, the DUT will reboot into netboot firmware
and start network image installation process to re-image.

Test Procedure
--------------
1. This test will first check if test image (when ``check_release_image`` is
   False) or release image (when ``check_release_image`` is True) version >=
   ``min_version``. If so, this test will pass.
2. If ``reimage`` is set to False, this test will fail.
3. If ``require_space`` is set to True, this test will wait for the user presses
   spacebar.
4. If ``use_netboot`` is set to True, this test will try to download
   netboot firmware from factory server and flash into AP firmware. Otherwise,
   download and install the selected component using ``cros_payload`` command.
   If the needed components are not available on factory server, this test will
   fail.
5. If ``use_netboot`` is set to True, The DUT will then reboot into netboot
   firmware and start network image installation process to reimage.

Dependency
----------
- If argument ``reimage`` is set to True, factory server must be set up and be
  ready for network image installation.
- If argument ``use_netboot`` is set to True, netboot firmware must be
  available on factory server.

Examples
--------
To check test image version is greater than or equal to 9876.5.4, add this in
test list::

  {
    "pytest_name": "check_image_version",
    "args": {
      "min_version": "9876.5.4",
      "reimage": false
    }
  }

Reimage if release image version is older than 9876.5.4 by flashing netboot
firmware and make pressing spacebar not needed::

  {
    "pytest_name": "check_image_version",
    "args": {
      "min_version": "9876.5.4",
      "check_release_image": true,
      "require_space": false
    }
  }

Reimage if test image version is greater than or equal to 9876.5.2012_12_21_2359
(loose format version) by flashing netboot firmware image on factory server::

  {
    "pytest_name": "check_image_version",
    "args": {
      "min_version": "9876.5.2012_12_21_2359",
      "loose_version": true,
    }
  }

Reimage if release image is older than the release_image version on factory
server using cros_payload::

  {
    "pytest_name": "check_image_version",
    "args": {
      "check_release_image": true,
      "use_netboot": false,
    }
  }
"""

from distutils import version
import logging
import os
import re

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.utils.arg_utils import Arg


class CheckImageVersionTest(test_case.TestCase):
  ARGS = [
      Arg('min_version', str, (
          'Minimum allowed test or release image version.'
          'None to follow the version on factory server.'), default=None),
      Arg('loose_version', bool, 'Allow any version number representation.',
          default=False),
      Arg('reimage', bool, 'True to re-image when image version mismatch.',
          default=True),
      Arg('require_space', bool,
          'True to require a space key press before re-imaging.', default=True),
      Arg('check_release_image', bool,
          'True to check release image instead of test image.', default=False),
      Arg('verify_rootfs', bool,
          'True to verify rootfs before install image.',
          default=True),
      Arg('use_netboot', bool,
          'True to image with netboot, otherwise cros_payload.', default=True)]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def WaitNetworkReady(self):
    while not self.dut.status.eth_on:
      self.ui.SetInstruction(_('Please connect to ethernet.'))
      self.Sleep(0.5)

  def runTest(self):
    # If this test stop unexpectedly during installing new image, we need to
    # check image version and verify Root FS to ensure the DUT is successfully
    # installed or not. The partition of Root FS is the last one to be written,
    # so the image version from lsb-release and the verification of Root FS can
    # ensure the result of installation.
    if self.CheckImageVersion() and self.VerifyRootFs():
      return

    if not self.args.reimage:
      self.FailTask('Image version is incorrect. Please re-image this device.')

    self.WaitNetworkReady()
    if self.args.require_space:
      self.ui.SetInstruction(
          _('Image version is incorrect. Press space to re-image.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    if self.args.use_netboot:
      component = update_utils.COMPONENTS.netboot_firmware
      destination = None
      callback = self.NetbootCallback
    else:
      self.assertTrue(
          self.args.check_release_image, 'Only release_image is supported.')
      component = update_utils.COMPONENTS.release_image
      destination = self.dut.partitions.rootdev
      callback = None
    self.ReImage(component, destination, callback)

  def NetbootCallback(self, component, destination, url):
    # TODO(hungte) Should we merge this with flash_netboot.py?
    del url  # Unused.
    fw_path = os.path.join(destination, component)
    self.ui.SetInstruction(_('Flashing {component}...', component=component))
    try:
      if self.dut.link.IsLocal():
        self.ui.PipeProcessOutputToUI(
            ['flash_netboot', '-y', '-i', fw_path, '--no-reboot'])
      else:
        with self.dut.temp.TempFile() as temp_file:
          self.dut.link.Push(fw_path, temp_file)
          factory_par = deploy_utils.CreateFactoryTools(self.dut)
          factory_par.CheckCall(
              ['flash_netboot', '-y', '-i', temp_file, '--no-reboot'], log=True)
      self.dut.CheckCall(['reboot'], log=True)
    except Exception:
      self.FailTask('Error flashing netboot firmware!')
    else:
      self.FailTask('Incorrect image version, DUT is rebooting to reimage.')

  def ReImage(self, component, destination, callback):
    updater = update_utils.Updater(
        component, spawn=self.ui.PipeProcessOutputToUI)
    if not updater.IsUpdateAvailable():
      self.FailTask('%s not available on factory server.' % component)

    self.ui.SetInstruction(_('Updating {component}....', component=component))
    updater.PerformUpdate(destination=destination, callback=callback)

  def CheckImageVersion(self):
    if self.args.min_version is None:
      # TODO(hungte) In future if we find it useful to reflash netboot for
      # updating test image, we can add test_image to update_utils and enable
      # fetching version here.
      self.assertTrue(
          self.args.check_release_image,
          'Empty min_version only allowed for check_release_image.')

      self.WaitNetworkReady()
      updater = update_utils.Updater(update_utils.COMPONENTS.release_image)
      # The 'release_image' component in cros_payload is using
      # CHROMEOS_RELEASE_DESCRIPTION for version string so we have to strip it
      # in future when supporting "re-image if remote is different".
      self.args.min_version = updater.GetUpdateVersion().split()[0]

      if not self.args.min_version:
        self.FailTask('Release image not available on factory server.')

    if self.args.check_release_image:
      ver = self.dut.info.release_image_version
      name = 'release_image'
    else:
      ver = self.dut.info.factory_image_version
      name = 'test_image'

    if ver is None:
      logging.warning('Can\'t find current version')
      return False

    testlog.LogParam(name=name, value=ver)
    expected = self.args.min_version
    version_format = (version.LooseVersion if self.args.loose_version else
                      version.StrictVersion)
    logging.info('Using version format: %r', version_format.__name__)
    logging.info('current version: %r, expected: %r', ver, expected)
    re_branched_image_version = re.compile(r'^R\d+-(\d+\.\d+\.\d+)$')
    ver_match = re_branched_image_version.match(ver)
    if ver_match:
      ver = ver_match.group(1)
    expected_match = re_branched_image_version.match(expected)
    if expected_match:
      expected = expected_match.group(1)
    if self.args.reimage and bool(ver_match) ^ bool(expected_match):
      logging.info('Attempt to re-image between different branch')
    # TODO(hungte) In future we may want 'exact' match more than min_version.
    return version_format(ver) >= version_format(expected)

  def VerifyRootFs(self):
    if self.args.check_release_image and self.args.verify_rootfs:
      factory_tool = deploy_utils.CreateFactoryTools(self.dut)
      exit_code = factory_tool.Call(
          ['gooftool', 'verify_rootfs', '--release_rootfs',
           self.dut.partitions.RELEASE_ROOTFS.path])
      return exit_code == 0
    return True
