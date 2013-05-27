# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Minijack web interface frontend service.

This configuration runs minijack frontend as a fastcgi.
"""


import logging
import os
import shutil
import zipfile

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.test.utils import TryMakeDirs
from cros.factory.utils.file_utils import TempDirectory


FRONTEND_DIR = 'frontend'
STATIC_DIR = 'static'
TEMPLATES_DIR = 'templates'
# TODO(rong): move to constants, or env.
FACTORY_SOFTWARE = 'factory.par'


def _IsFrontendFile(name):
  """Checks par member is a frontend file or not.

  Args:
    name: a relative file pathname returned from zipfile.namelist().

  Returns:
    True if the name is under frontend static or templates folder. Otherwise
    False.
  """
  return (isinstance(name, basestring) and
          (name.startswith('cros/factory/minijack/frontend/static/') or
           name.startswith('cros/factory/minijack/frontend/templates/')))


class MinijackFrontendService(ServiceBase):
  """Minijack frontend configuration.

  Args:
    dummy_config: Launcher YAML config dictionary.
  """
  def __init__(self, dummy_config):
    # ServiceBase inherits from old-style ProcessProtocol.
    ServiceBase.__init__(self)

    mjfe_executable = os.path.join(env.runtime_dir, 'minijack_frontend')
    self.SetConfig({
        'executable': mjfe_executable,
        'name': 'minijackfesvc',
        'args': [''],
        'path': env.runtime_dir,
        'logpipe': False,
        'auto_restart': True})

    # Create symlink and folders.
    factory_software = os.path.join(env.runtime_dir, FACTORY_SOFTWARE)
    if not os.path.isfile(mjfe_executable):
      os.symlink(factory_software, mjfe_executable)
    frontend_dir = os.path.join(env.runtime_dir, FRONTEND_DIR)
    static_dir = os.path.join(frontend_dir, STATIC_DIR)
    templates_dir = os.path.join(frontend_dir, TEMPLATES_DIR)
    TryMakeDirs(frontend_dir)
    if os.path.isdir(static_dir):
      shutil.rmtree(static_dir)
    if os.path.isdir(templates_dir):
      shutil.rmtree(templates_dir)

    # Extract frontend static files and rendering templates.
    with TempDirectory() as temp_dir:
      # zipfile extracts full pathname, the frontend dir inside temp folder is
      # [temp]/cros/factory/minijack/frontend
      extracted_frontend = os.path.join(temp_dir, 'cros', 'factory',
                                        'minijack', 'frontend')
      extracted_static = os.path.join(extracted_frontend, STATIC_DIR)
      extracted_templates = os.path.join(extracted_frontend, TEMPLATES_DIR)
      with zipfile.ZipFile(factory_software) as par:
        members = filter(_IsFrontendFile, par.namelist())
        par.extractall(temp_dir, members)
        # Move static and templates folder to destination folder, or create
        # them.
        if os.path.isdir(extracted_static):
          shutil.move(extracted_static, static_dir)
        else:
          logging.warning('MJFE: factory.par static folder not found.')
          TryMakeDirs(static_dir)
        if os.path.isdir(extracted_templates):
          shutil.move(extracted_templates, templates_dir)
        else:
          logging.warning('MJFE: factory.par template folder not found.')
          TryMakeDirs(templates_dir)


Service = MinijackFrontendService
