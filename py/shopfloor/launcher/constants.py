# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uber shopfloor constants, accessors and their helper functions."""

# Constants
DEFAULT_BIND_ADDRESS = '0.0.0.0'
DEFAULT_BIND_PORT = 8082
DEFAULT_RSYNC_PORT = DEFAULT_BIND_PORT + 1
COMMAND_PORT = DEFAULT_BIND_PORT + 2
DEFAULT_FCGI_PORT = DEFAULT_BIND_PORT + 3

SHOPFLOOR_INSTALL_DIR = '/var/db/factory'
SHOPFLOOR_SYMLINK_DIR = '/usr/local/bin'
FCGI_EXEC = 'shopfloor.fcgi'
RESOURCES_DIR = 'resources'
UPDATES_DIR = 'updates'
LOGS_DIR = 'log'

# Shared shopfloor server constants
FACTORY_SOFTWARE = 'factory.par'
SHOPFLOOR_DATA = 'shopfloor_data'

# Maximum number of file descriptors when run as root
HTTPD_MAX_FDS = 32768
# Maximum number of connections
HTTPD_MAX_CONN = HTTPD_MAX_FDS / 2

