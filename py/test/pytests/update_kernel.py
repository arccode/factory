# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Applies new kernel to DUT (for testing)."""

import os
import tempfile
import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneScrollableSection
from cros.factory.utils import process_utils

_TEST_TITLE = MakeLabel('Update Kernel', u'更新 Kernel')
_CSS = '#state {text-align:left;}'


class UpdateFirmwareTest(unittest.TestCase):
  ARGS = [
      # TODO(hungte) Support compressed image, or download from Omaha.
      Arg('kernel_image', str, 'Full path of kernel.bin',
          default='/usr/local/factory/board/kernel.bin'),
  ]

  def setUp(self):
    self.assertTrue(os.path.isfile(self.args.kernel_image),
                    msg='%s is missing.' % self.args.kernel_image)
    self._ui = UI()
    self._template = OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def UpdateKernel(self):
    """Apply new kernel.

    Gets current kernel config, re-sign by make_dev_ssd, then write into system.
    """
    rootdev = process_utils.CheckOutput(["rootdev", "-s"]).strip()
    if rootdev.endswith('3'):
      kerndev = rootdev[:-1] + '2'
    elif rootdev.endswith('5'):
      kerndev = rootdev[:-1] + '4'
    else:
      self._ui.Fail('Unable to determine kernel location (%s)' % rootdev)
      return
    kernel_id = kerndev[-1:]

    kernel_config = process_utils.CheckOutput(["dump_kernel_config", kerndev])
    # Directly write into kernel partition.
    with open(kerndev, 'wb') as f:
      f.write(open(self.args.kernel_image).read())

    config_suffix = ".%s" % kernel_id
    with tempfile.NamedTemporaryFile(suffix=config_suffix) as config:
      config.write(kernel_config)
      config.flush()
      process_utils.LogAndCheckCall([
          "/usr/share/vboot/bin/make_dev_ssd.sh", "--partitions", kernel_id,
          "--set_config", config.name[:-len(config_suffix)]])
    self._ui.Pass()

  def runTest(self):
    threading.Thread(target=self.UpdateKernel).start()
    self._ui.Run()
