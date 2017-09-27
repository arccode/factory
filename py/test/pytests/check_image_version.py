# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Check release or test OS image version on internal storage.

Description
-----------
This test checks if Chrome OS test image or release image version in
'/etc/lsb-release' are greater than or equal to the value of argument
``min_version``. If the version is too old and argument ``reimage`` is set to
True, reflash either local netboot firmware or remote netboot firmware from
factory server (e.g., Mini-Omaha or Umpire). After that, the DUT will reboot
into netboot firmware and start network image installation process to reimage.

Test Procedure
--------------
1. This test will first check if test image (when ``check_release_image`` is
   False) or release image (when ``check_release_image`` is True) version >=
   ``min_version``. If so, this test will pass.
2. If ``reimage`` is set to False, this test will fail.
3. If ``require_space`` is set to True, this test will wait for the user presses
   spacebar.
4. If ``download_from_server`` is set to True, this test will try to download
   netboot firmware from factory server to the path indicated by argument
   ``netboot_fw``. If there is no available netboot firmware on factory server,
   this test will fail.
5. Main firmware will be flashed with the firmware image in path ``netboot_fw``.
6. The DUT will then reboot into netboot firmware and start network image
   installation process to reimage.

Dependency
----------
- If argument ``reimage`` is set to True, factory server must be set up and be
  ready for network image installation.
- If argument ``download_from_server`` is set to True, netboot firmware must be
  available on factory server. If ``download_from_server`` is set to False,
  netboot firmware must be prepared in the path that argument ``netboot_fw``
  indicated.

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

Reimage if release image version is older than 9876.5.4 by flashing local
netboot firmware, which is located in '/usr/local/factory/board/image.net.bin',
and make pressing spacebar not needed::

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
      "download_from_server": true
    }
  }
"""

from distutils import version
import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.event_log import Log
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_task
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.tools import flash_netboot
from cros.factory.utils.arg_utils import Arg


_CSS = """
.start-font-size {
  font-size: 2em;
}
"""

# Messages for tasks
_MSG_VERSION_MISMATCH = i18n_test_ui.MakeI18nLabelWithClass(
    'Image version is incorrect. Please re-image this device.',
    'start-font-size test-error')
_MSG_NETWORK = i18n_test_ui.MakeI18nLabel('Please connect to ethernet.')
_MSG_NO_FIRMWARE_ON_SERVER = i18n_test_ui.MakeI18nLabel(
    'Netboot firmware not available on factory server.')
_MSG_NETBOOT = i18n_test_ui.MakeI18nLabel(
    'Image version is incorrect. Press space to re-image.')
_MSG_REIMAGING = i18n_test_ui.MakeI18nLabel('Flashing netboot firmware...')
_MSG_FLASH_ERROR = i18n_test_ui.MakeI18nLabelWithClass(
    'Error flashing netboot firmware!', 'start-font-size test-error')


class ImageCheckTask(test_task.TestTask):

  def __init__(self, test):
    super(ImageCheckTask, self).__init__()
    self._test = test
    self.dut = test.dut

  def CheckNetwork(self):
    while not self.dut.status.eth_on:
      time.sleep(0.5)
      self._test.template.SetState(_MSG_NETWORK)

  def PromptReimage(self):
    self._test.template.SetState(_MSG_NETBOOT)
    self._test.ui.BindKey(test_ui.SPACE_KEY, self.Reimage)

  def Reimage(self):
    # TODO(b/64881268): Run cros_payload to update release image directly.
    if self._test.args.download_from_server:
      updater = update_utils.Updater(update_utils.COMPONENTS.netboot_firmware)
      if not updater.IsUpdateAvailable():
        self._test.template.SetState(_MSG_NO_FIRMWARE_ON_SERVER)
        return
      updater.PerformUpdate(destination=self._test.args.netboot_fw)

    self._test.template.SetState(_MSG_REIMAGING)
    try:
      with self.dut.temp.TempFile() as temp_file:
        self.dut.link.Push(self._test.args.netboot_fw, temp_file)
        factory_par = deploy_utils.CreateFactoryTools(self.dut)
        factory_par.CheckCall(
            ['flash_netboot', '-y', '-i', temp_file, '--no-reboot'], log=True)
      self.dut.CheckCall(['reboot'], log=True)
      self.Fail('Incorrect image version, DUT is rebooting to reimage.')
    except Exception:
      self._test.template.SetState(_MSG_FLASH_ERROR)

  def CheckImageVersion(self):
    if self._test.args.check_release_image:
      ver = self.dut.info.release_image_version
    else:
      ver = self.dut.info.factory_image_version
    Log('image_version', version=ver)
    version_format = (version.LooseVersion if self._test.args.loose_version else
                      version.StrictVersion)
    logging.info('Using version format: %r', version_format.__name__)
    logging.info('current version: %r', ver)
    logging.info('expected version: %r', self._test.args.min_version)
    return version_format(ver) < version_format(self._test.args.min_version)

  def Run(self):
    if self.CheckImageVersion():
      if self._test.args.reimage:
        self.CheckNetwork()
        if self._test.args.require_space:
          self.PromptReimage()
        else:
          self.Reimage()
      else:
        self._test.template.SetState(_MSG_VERSION_MISMATCH)
      return
    self.Pass()


class CheckImageVersionTest(unittest.TestCase):
  ARGS = [
      Arg('min_version', str, 'Minimum allowed test or release image version.'),
      Arg('loose_version', bool, 'Allow any version number representation.',
          default=False),
      Arg('netboot_fw', str, 'The path to netboot firmware image.',
          default=flash_netboot.DEFAULT_NETBOOT_FIRMWARE_PATH),
      Arg('reimage', bool, 'True to re-image when image version mismatch.',
          default=True),
      Arg('require_space', bool,
          'True to require a space key press before reimaging.', default=True),
      Arg('check_release_image', bool,
          'True to check release image instead of test image.', default=False),
      Arg('download_from_server', bool,
          'True to download netboot firmware image from factory server.',
          default=False)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self._task_list = [ImageCheckTask(self)]
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)

  def runTest(self):
    test_task.TestTaskManager(self.ui, self._task_list).Run()
