# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Retrieve JSON config file from either an USB stick or a factory server.

Description
-----------
This pytest retrieves the config file from a specified source, so a following
pytest can use config_utils to load specfic config data.

The config file can be fecthed from two types of sources:
1. Factory server
2. USB stick

To fetch a config file from a factory server, you should put the config
file under the 'parameters' folders, and specify the `data_method` to
FACTORY_SERVER.

To fetch a config file from a USB stick, you can put the file at any partition
you want, as long as the partition and file system on the USB stick can be
recognized by the operating system. The `data_method` should be set to 'USB',
and if there are several partitions on the USB stick, the argument
`usb_dev_parition` should be set to specify the partition you placed the config
file.

Test Procedure
--------------
If `data_method` is set to 'FACTORY_SERVER', no action needs to be done.

If `data_method` is set to 'USB', then:
1. Insert the USB stick
2. Wait for completion

Dependency
----------
Depends on 'udev' and 'pyudev' python module to monitor USB insertion.

Examples
--------
Assume the config file is located at 'foo/bar.json' under the remote source
(i.e., a factory server, or a USB stick).

The JSON config can be loaded from the factory server by::

  {
    "pytest_name": "retrieve_config",
    "args": {
      "config_retrieve_path": "foo/bar.json"
    }
  }

To load the JSON config from a USB stick, add this in test list::

  {
    "pytest_name": "retrieve_config",
    "args": {
      "data_method": "USB",
      "config_retrieve_path": "foo/bar.json"
    }
  }
"""


import logging
import os
import threading
import time
import unittest

from cros.factory.test import session
from cros.factory.test import server_proxy
from cros.factory.test.utils import media_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


DATA_METHOD = type_utils.Enum(['USB', 'FACTORY_SERVER'])


class RetrieveConfigException(Exception):
  pass


class RetrieveConfig(unittest.TestCase):
  """RetrieveConfig main class.

  The USB data method is unstable and not really fits to our factory flow. We
  still keep this method for some usage purpose.

  If Arg config_save_name=None , the RetrieveConfig will save the config file
  directly to the config_save_dir, and it won't keep the relatve structures
  retrieving from. For example,

  Remote file structure:

  ...
  |__ als
      |__ als_fixture.schema.json

  Then it will save the config to (assume config_save_dir=None),

  var
  |__ factory
      |__ config
          |__ als_fixture.schema.json
  """

  ARGS = [
      Arg('data_method',
          DATA_METHOD,
          'The method to retrieve config.',
          default=DATA_METHOD.FACTORY_SERVER),
      Arg('config_retrieve_path',
          str,
          'The path to the config file to retrieve from.'),
      Arg('config_save_dir',
          str,
          'The directory path to the config file to place at;'
          'defaults to RuntimeConfigDirectory in config_utils.json.',
          default=None),
      Arg('config_save_name',
          str,
          'The config name saved in the config_save_dir; The name should '
          'suffix with ".json". if None then defaults to its origin name.',
          default=None),
      Arg('local_ip',
          str,
          'Local IP address for connecting to the factory server '
          'when data_method = FACTORY_SERVER. Set as None to use DHCP.',
          default=None),
      Arg('usb_dev_partition',
          int,
          'The partition of the usb_dev_path to be mounted. If None, will try '
          'to mount the usb_dev_path without partition number.',
          default=None),
  ]

  def setUp(self):
    self.args.config_save_dir = (self.args.config_save_dir or
                                 config_utils.GetRuntimeConfigDirectory())
    self.args.config_save_name = self.args.config_save_name or os.path.basename(
        self.args.config_retrieve_path)
    if not self.args.config_save_name.endswith('.json'):
      raise RetrieveConfigException('Config name should suffix with ".json".')

    self.config_save_path = os.path.join(self.args.config_save_dir,
                                         self.args.config_save_name)

    self.usb_dev_path = None
    self.usb_ready_event = None

  def runTest(self):
    file_utils.TryMakeDirs(os.path.dirname(self.config_save_path))
    if self.args.data_method == DATA_METHOD.USB:
      self._RetrieveConfigFromUSB()
    elif self.args.data_method == DATA_METHOD.FACTORY_SERVER:
      self._RetrieveConfigFromFactoryServer()
    else:
      raise ValueError('Unknown data_method.')

  def _RetrieveConfigFromFactoryServer(self):
    """Loads parameters from a factory server."""
    try:
      session.console.info('Retrieving %s from factory server.',
                           self.args.config_retrieve_path)
      proxy = server_proxy.GetServerProxy()
      content = proxy.GetParameter(
          self.args.config_retrieve_path).data
      with open(self.config_save_path, 'w') as f:
        f.write(content)
      logging.info('Saved config to %s.', self.config_save_path)
    except Exception as e:
      logging.exception('Failed to retrieve config from factory server.')
      raise RetrieveConfigException(str(e))

  def _RetrieveConfigFromUSB(self):
    """Loads json config from USB drive."""
    self.usb_ready_event = threading.Event()
    monitor = media_utils.RemovableDiskMonitor()
    monitor.Start(on_insert=self._OnUSBInsertion, on_remove=self._OnUSBRemoval)

    try:
      self.usb_ready_event.wait()
      self._MountUSBAndCopyFile()
    finally:
      monitor.Stop()
    logging.info('Saved config to %s.', self.config_save_path)

  def _MountUSBAndCopyFile(self):
    session.console.info('Mounting USB (%s, %s).', self.usb_dev_path,
                         self.args.usb_dev_partition)
    with media_utils.MountedMedia(self.usb_dev_path,
                                  self.args.usb_dev_partition) as mount_point:
      time.sleep(0.5)
      pathname = os.path.join(mount_point, self.args.config_retrieve_path)
      session.console.info('Retrieving %s from USB.', pathname)
      if not os.path.exists(pathname):
        raise ValueError(
            'File %r does not exist or it is not a file.' % pathname)
      try:
        file_utils.CopyFileSkipBytes(pathname, self.config_save_path, 0)
      except IOError as e:
        logging.error('Failed to copy file %s to %s, %r', pathname,
                      self.config_save_path, e)
        raise RetrieveConfigException(str(e))

  def _OnUSBInsertion(self, device):
    self.usb_dev_path = device.device_node
    self.usb_ready_event.set()

  def _OnUSBRemoval(self, device):
    del device  # unused
    self.usb_ready_event.clear()
    self.usb_dev_path = None
