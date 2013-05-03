# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""
Shop Floor Launcher shared environment

To use it, import the class and use class variables and class methods without
instanciate.

Example:
  from cros.factory.shopfloor.launcher import env
  system_dir = env.runtime_dir
"""


import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants

# ShopFloor runtime root dir
runtime_dir = constants.SHOPFLOOR_INSTALL_DIR
# ShopFloor bind address
bind_address = constants.DEFAULT_BIND_ADDRESS
# ShopFloor httpd bind port
bind_port = constants.DEFAULT_BIND_PORT
# Factory update rsync server port
rsync_port = constants.DEFAULT_RSYNC_PORT
# FastCGI service bind port
fcgi_port = constants.DEFAULT_FCGI_PORT

# Launcher config holds the dictionary deserialized from YAML config file
launcher_config = {}
# Launcher services contains all external applications launched by shopfloord
launcher_services = []

def GetFCGIExec():
  """Gets FastCGI program path."""
  return os.path.join(runtime_dir, constants.FCGI_EXEC)

def GetResourcesDir():
  """Gets shopfloor resources dir."""
  return os.path.join(runtime_dir, constants.RESOURCES_DIR)

def GetUpdatesDir():
  """Gets update dir."""
  return os.path.join(runtime_dir, constants.UPDATES_DIR)

