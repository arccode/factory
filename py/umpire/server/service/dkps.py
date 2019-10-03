# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""DKPS service for DRM keys management."""

import os
import stat
import subprocess
import sys

from cros.factory.umpire.server.service import umpire_service


PYTHON_PATH = sys.executable


class DKPSService(umpire_service.UmpireService):
  """DKPS service."""

  def CreateProcesses(self, umpire_config, env):
    # pylint: disable=unused-argument
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """
    dkps_data_dir = os.path.join(env.umpire_data_dir, 'dkps')
    gnupg_dir = os.path.join(dkps_data_dir, 'gnupg')
    database_path = os.path.join(dkps_data_dir, 'dkps.db')
    dkps_file_path = os.path.join(
        env.server_toolkit_dir, 'py', 'dkps', 'dkps.py')

    # create folders (recursively) if necessary
    if not os.path.isdir(dkps_data_dir):
      os.makedirs(dkps_data_dir)
    if not os.path.isdir(gnupg_dir):
      # GnuPG's folder should only be accessible by the owner
      os.makedirs(gnupg_dir, stat.S_IRWXU)

    # global options: set log file path, database path, and GnuPG home dir
    global_opts = [
        dkps_file_path,
        '--log_file_path', os.path.join(env.log_dir, 'dkps.log'),
        '--database_file_path', database_path,
        '--gnupg_homedir', gnupg_dir]

    # workaround for python-gnupg: python-gnupg accesses either
    # os.environ['LOGNAME'] or os.environ['USERNAME'], one of them must exist or
    # python-gnupg will raise a KeyError
    os.environ.setdefault('LOGNAME', 'dkps')

    # initialize DKPS if necessary
    if not os.path.isfile(database_path):
      subprocess.check_call([PYTHON_PATH] + global_opts + ['init'])

    proc_config = {
        'executable': PYTHON_PATH,
        'name': 'dkps',
        'args': global_opts + ['listen'],
        'path': dkps_data_dir}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
