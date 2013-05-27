# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Rsync service.

This service configures launcher to start rsync daemon that serves factory
bundle update and log upload.
"""

import glob
import logging
import os
import shutil
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.shopfloor.launcher.utils import Md5sum
from cros.factory.test.utils import TryMakeDirs

RSYNCD_CONFIG_TEMPLATE = '''port = %(port)d
pid file = %(pidfile)s
log file = %(logfile)s
use chroot = no
'''
RSYNCD_CONFIG_MODULE_PATH_TEMPLATE = '''[%(module)s]
  path = %(path)s
  read only = %(read_only)s
'''
LATEST_MD5FILE = 'latest.md5sum'


class RsyncService(ServiceBase):
  """Rsync configuration.

  Args:
    yaml_config: Launcher YAML config dictionary.
  """
  def __init__(self, config):
    # ServiceBase inherits from an old-style python class.
    ServiceBase.__init__(self)

    config_file = os.path.join(env.runtime_dir, 'rsyncd.conf')
    log_file = os.path.join(env.runtime_dir, 'log', 'rsync.log')
    pid_file = os.path.join(env.runtime_dir, 'run', 'rsync.pid')
    if os.path.exists(pid_file):
      os.unlink(pid_file)

    rsync_config = RSYNCD_CONFIG_TEMPLATE % dict(
        port=constants.DEFAULT_RSYNC_PORT,
        pidfile=pid_file,
        logfile=log_file)

    # Factory update module
    hwid_files = glob.glob(os.path.join(env.GetUpdatesDir(), 'hwid_*.sh'))
    update_bundle_path = os.path.join(env.GetUpdatesDir(), 'factory')
    map(os.unlink, hwid_files)
    if 'updater' in config:
      TryMakeDirs(env.GetUpdatesDir())
      TryMakeDirs(update_bundle_path)
      rsync_config += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % dict(
          module='factory',
          path=update_bundle_path,
          read_only='yes')
      if 'update_bundle' in config['updater']:
        self._PrepareUpdateBundle(config['updater']['update_bundle'])
      if 'hwid_bundle' in config['updater']:
        self._PrepareHwidBundle(config['updater']['hwid_bundle'])
    else:
      latest_md5file = os.path.join(update_bundle_path, LATEST_MD5FILE)
      if os.path.isfile(latest_md5file):
        os.unlink(latest_md5file)


    # Log upload module
    upload_path = os.path.join(env.runtime_dir, 'upload_logs')
    TryMakeDirs(upload_path)
    rsync_config += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % dict(
        module='system_logs',
        path=upload_path,
        read_only='no')

    with open(config_file, 'w') as f:
      f.write(rsync_config)

    svc_conf = {
      'executable': 'rsync',
      'name': 'rsyncsvc',
      'args': [
        '--daemon',
        '--no-detach',
        '--config=%s' % config_file],
      'path': env.runtime_dir,
      'logpipe': False,
      'auto_restart': True}
    self.SetConfig(svc_conf)

  def _PrepareUpdateBundle(self, bundle):
    bundle_file = os.path.join(env.GetResourcesDir(), bundle)
    bundle_dir = os.path.join(env.GetUpdatesDir(), 'factory')
    latest_md5file = os.path.join(bundle_dir, LATEST_MD5FILE)
    latest_md5sum = None
    bundle_md5sum = None
    # Check latest deployed update bundle
    if os.path.isfile(latest_md5file):
      with open(latest_md5file, 'r') as f:
        latest_md5sum = f.readline().strip()
      if latest_md5sum[0:8] == bundle[-8:]:
        return
    # Check other deployed bundle
    bundle_md5sum = Md5sum(bundle_file)
    dest_dir = os.path.join(bundle_dir, bundle_md5sum)
    if not os.path.isfile(os.path.join(dest_dir, 'factory', 'MD5SUM')):
      if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
      TryMakeDirs(dest_dir)
      logging.info('Stagging into %s', dest_dir)
      try:
        subprocess.check_call(['tar', '-xjf', bundle_file, '-C', dest_dir])
      except subprocess.CalledProcessError as e:
        logging.exception('Failed to extract update bundle %s to %s',
                          bundle, dest_dir)
        raise e
      with open(os.path.join(dest_dir, 'factory', 'MD5SUM'), 'w') as f:
        f.write(bundle_md5sum)
    with open(latest_md5file, 'w') as f:
      f.write(bundle_md5sum)

  def _PrepareHwidBundle(self, bundle):
    os.symlink(os.path.join(env.GetResourcesDir(), bundle),
               os.path.join(env.GetUpdatesDir(), bundle[0:-9]))


Service = RsyncService
