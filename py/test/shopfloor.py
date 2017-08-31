# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for Factory Shop Floor.

This module provides a simple interface for all factory tests to access Chrome
OS factory server.

The common flow is:
  - Sets shop floor server URL by shopfloor.set_server_url(url).
  - Get proxy object by shopfloor.get_instance() or GetShopfloorConnection().
  - Invoke RPC by proxy object.

For the protocol details, check:
 src/platform/factory/py/shopfloor/factory_server.py.
"""

import contextlib
import json
import os
import time
import urllib2
import xmlrpclib
from xmlrpclib import Binary

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test import server_proxy
from cros.factory.umpire.client import umpire_client
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


# Default timeout and retry interval for getting a valid shopfloor instance.
SHOPFLOOR_TIMEOUT_SECS = 10  # Timeout for shopfloor connection.
SHOPFLOOR_RETRY_INTERVAL_SECS = 10  # Seconds to wait between retries.

# Some tests refer to "shopfloor.Fault" so we need to export it from
# shopfloor.
Fault = xmlrpclib.Fault

# ----------------------------------------------------------------------------
# Utility Functions


def set_server_url(url):
  """Sets default shop floor server URL for further calls."""
  server_proxy.SetServerURL(url)


def get_server_url():
  """Gets shop floor server URL."""
  return server_proxy.GetServerURL()


def get_instance(url=None, timeout=None, quiet=False):
  """Gets an instance (for client side) to access the shop floor server.

  Args:
    url: URL of the shop floor server. If None, use the value in
      factory shared data.
    timeout: If not None, the timeout in seconds. This timeout is for RPC
      calls on the proxy, not for get_instance() itself.
    quiet: Suppresses error messages when shopfloor can not be reached.

  Returns:
    A TimeoutUmpireServerProxy object that can work with either
    simple XMLRPC server or Umpire server.
  """
  return server_proxy.GetServerProxy(url=url, timeout=timeout, quiet=quiet)


def GetShopfloorConnection(
    timeout_secs=SHOPFLOOR_TIMEOUT_SECS,
    retry_interval_secs=SHOPFLOOR_RETRY_INTERVAL_SECS):
  """Returns a shopfloor client object.

  Try forever until a connection of shopfloor is established.

  Args:
    timeout_secs: Timeout for shopfloor connection.
    retry_interval_secs: Seconds to wait between retries.
  """
  factory.console.info('Connecting to shopfloor...')
  iteration = 0
  while True:
    iteration += 1
    try:
      shopfloor_client = get_instance(timeout=timeout_secs)
      shopfloor_client.Ping()
      break
    except Exception:
      exception_string = debug_utils.FormatExceptionOnly()
      # Log only the exception string, not the entire exception,
      # since this may happen repeatedly.
      factory.console.info(
          'Unable to sync with shopfloor server in iteration [%3d], '
          'retry after [%2dsecs]: %s',
          iteration, retry_interval_secs, exception_string)
    time.sleep(retry_interval_secs)
  return shopfloor_client


def UploadAuxLogs(file_paths, ignore_on_fail=False, dir_name=None):
  """Attempts to upload arbitrary files to the shopfloor server.
  Args:
    file_paths: file paths which would like to be uploaded.
    ignore_on_fail: do not raise exception if the value is True.
    dir_name: relative directory on shopfloor.
  """
  shopfloor_client = GetShopfloorConnection()
  for file_path in file_paths:
    try:
      chunk = open(file_path, 'r').read()
      log_name = os.path.basename(file_path)
      if dir_name:
        log_name = os.path.join(dir_name, log_name)
      factory.console.info('Uploading %s', log_name)
      start_time = time.time()
      shopfloor_client.SaveAuxLog(log_name, Binary(chunk))
      factory.console.info('Successfully synced %s in %.03f s',
                           log_name, time.time() - start_time)
    except Exception:
      if ignore_on_fail:
        factory.console.info(
            'Failed to sync with shopfloor for [%s], ignored',
            log_name)
      else:
        raise
