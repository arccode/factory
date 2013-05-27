# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Reports archive service."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import REPORTS_DIR
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.archive_reports import ARCHIVE_DIR
from cros.factory.shopfloor.launcher.archive_reports import RECYCLE_DIR
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.test.utils import TryMakeDirs


class ArchiveService(ServiceBase):
  """Report archive configuration.

  Args:
    dummy_config: Launcher YAML config dictionary.
  """
  def __init__(self, dummy_config):
    # ServiceBase is an old-style python class.
    ServiceBase.__init__(self)

    archiver_executable = os.path.join(env.runtime_dir, 'archive_reports')
    shopfloor_data = os.path.join(env.runtime_dir, constants.SHOPFLOOR_DATA)
    reports_dir = os.path.join(shopfloor_data, REPORTS_DIR)
    recycle_dir = os.path.join(shopfloor_data, RECYCLE_DIR)
    archive_dir = os.path.join(shopfloor_data, ARCHIVE_DIR)
    svc_conf = {
      'executable': archiver_executable,
      'name': 'archive_reports',
      'args': ['--period', '10'],
      'path': env.runtime_dir,
      'logpipe': True,
      'auto_restart': True}
    self.SetConfig(svc_conf)

    # Creates archiver symlink and folders.
    if not os.path.isfile(archiver_executable):
      os.symlink(os.path.join(env.runtime_dir, constants.FACTORY_SOFTWARE),
                 archiver_executable)
    # Archiver moves archived reports from shopfloor_data/reports to
    # shopfloor/recycle_bin.
    TryMakeDirs(shopfloor_data)
    TryMakeDirs(archive_dir)
    TryMakeDirs(recycle_dir)
    TryMakeDirs(reports_dir)

Service = ArchiveService
