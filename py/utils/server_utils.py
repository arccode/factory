# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Server-related utilities...'''


import logging
import os
from collections import namedtuple

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess



RSYNCD_CONFIG_TEMPLATE = '''port = %(port)d
pid file = %(pidfile)s
log file = %(logfile)s
use chroot = no
'''
RSYNCD_CONFIG_MODULE_PATH_TEMPLATE = '''[%(module)s]
  path = %(path)s
  read only = %(read_only)s
'''


RsyncModule = namedtuple('RsyncModule', ['module', 'path', 'read_only'])
# pylint: disable=W0105
"""The tuple to represent a module setting in rsync config file.
[<module>]
  path = <path>
  read only = <read_only>

  Props:
    module: The module name.
    path: The path of this module.
    read_only: A bool, which will be mapped to yes/no in the config file.
"""


def StartRsyncServer(port, state_dir, modules):
  """Starts rsync server.

  Args:
    port: Port to run rsyncd.
    state_dir: Directory of conf, pid, log file.
    modules: A list of RsyncModule to specify the modules to serve.
  """
  configfile = os.path.join(state_dir, 'rsyncd.conf')
  pidfile = os.path.join(state_dir, 'rsyncd.pid')
  if os.path.exists(pidfile):
    # Since rsyncd will not overwrite it if it already exists
    os.unlink(pidfile)
  logfile = os.path.join(state_dir, 'rsyncd.log')
  data = RSYNCD_CONFIG_TEMPLATE % dict(port=port,
                                       pidfile=pidfile,
                                       logfile=logfile)
  for (module, path, read_only) in modules:
    read_only = 'yes' if read_only else 'no'
    data += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % dict(module=module,
                                                      path=path,
                                                      read_only=read_only)
  with open(configfile, 'w') as f:
    f.write(data)

  p = Spawn(['rsync', '--daemon', '--no-detach', '--config=%s' % configfile],
            log=True)
  logging.info('Rsync server (pid %d) started on port %d', p.pid, port)
  return p


def StopRsyncServer(rsyncd_process):
  logging.info('Stopping rsync server (pid %d)', rsyncd_process.pid)
  TerminateOrKillProcess(rsyncd_process)
  logging.debug('Rsync server stopped')
