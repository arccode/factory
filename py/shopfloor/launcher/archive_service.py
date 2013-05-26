# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Reports archive service."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import env
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

    svc_conf = {
      'executable': os.path.join(env.runtime_dir, 'archive_reports'),
      'name': 'archive_reports',
      'args': ['--period', '10'],
      'path': env.runtime_dir,
      'logpipe': True,
      'auto_restart': True}
    self.SetConfig(svc_conf)

    TryMakeDirs(os.path.join(env.runtime_dir, 'shopfloor_data', 'reports'))
    TryMakeDirs(os.path.join(env.runtime_dir, 'shopfloor_data', 'recycle_bin'))

Service = ArchiveService
