#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A command line tool using UmpireServerProxy to connect to Umpire server."""

import argparse
import logging
import os
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.client import umpire_client
from cros.factory.umpire.client import umpire_server_proxy


DEFAULT_TEST_DATA = 'testdata/umpire_test_data.yaml'
DEFAULT_SERVER_URI = 'http://10.3.0.1:9090'


class FakeClientInfo(object):
  """Fake client info which implements UmpireClientInfoInterface."""
  __implements__ = (umpire_client.UmpireClientInfoInterface)

  def __init__(self, dut):
    """Initializes a fake client info.

    Args:
      dut: A dict containing client info, e.g.
        sn: 'TESTDEV002'
        mlb_sn: 'TESTMLB002'
        board: 'daisy_spring'
        firmware: '3000.0.0'
        ec: '3000.0.0'
        mac.eth0: 'FF:FF:FF:FF:FF:FF'
        mac.wlan0: 'EE:EE:EE:EE:EE:EE'

    Properties:
      dut: The same as dut in Args.
    """
    logging.debug('Initializing a FakeClientInfo with dut = %r', dut)
    self.dut = dut

  def Update(self):
    """Always returns False.

    This tool does not support changing client info.
    """
    return False

  def GetXUmpireDUT(self):
    """Returns client info in the format of X-Umpire-DUT.

    Returns:
      A string containing X-Umpire-DUT in the format of
      'sn=TESTDEV002; mlb_sn=TESTMLB002;...'.
    """
    info = ['%s=%s' % (k, v) for k, v in self.dut['X-Umpire-DUT'].iteritems()]
    ret = '; '.join(info)
    logging.debug('GetXUmpireDUT returns %r', ret)
    return ret

  def GetDUTInfoComponents(self):
    """Gets dut_info argument for GetUpdate method.

    Returns:
      A dict containing x_umpire_dut and components.
    """
    # TODO(cychiang) Implement this method so we can test GetUpdate method.
    raise NotImplementedError


class UmpireServerProxyCLI(object):
  """The main class of Umpire server proxy command line tool.

  This tool let user test Umpire server proxy and Umpire server
  connection and method calls. Fake client info can be specified in the test
  data yaml file. Method can be specified in command line argument.
  If the method to call has arguments, they can be specified in test data yaml
  file.

  Properties:
    args: Parsed command line arguments.
    fake_client_info: A FakeClientInfo object.
    data: Data read from test data yaml file.
    proxy: An UmpireServerProxy object.
  """

  def __init__(self):
    self.args = None
    self.fake_client_info = None
    self.data = None
    self.proxy = None

  def Main(self):
    """Connects to a server using Umpire server proxy with fake DUT info."""
    self.ParseArgs()
    self.LoadTestData()
    self.SetActiveDUT()
    self.InitConnection()
    self.CallMethod()

  def ParseArgs(self):
    parser = argparse.ArgumentParser(
        description='Using UmpireServerProxy to connect to an Umpire server '
        'for testing. Fake client info and method arguments can be specified '
        'in test data yaml file.')
    parser.add_argument(
        '--test-data', '-t', default=None,
        help='Path to the test data yaml file. The default file '
             ' is %s' % DEFAULT_TEST_DATA)
    parser.add_argument(
        '--dut', '-d', default=None,
        help='Name of the testing dut specified in test data yaml file.')
    parser.add_argument(
        '--server-uri', '-s', default=DEFAULT_SERVER_URI,
        help='Umpire server URI')
    parser.add_argument(
        '--verbose', '-v', default=None, action='store_true',
        help='Set logging level to DEBUG.')
    parser.add_argument(
        '--method', '-m', default=None, help='The method to call through '
        'proxy. Arguments are automatically set from test data if any.')

    self.args = parser.parse_args()

    logging.basicConfig(
        format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s',
        level=logging.DEBUG if self.args.verbose else logging.INFO)

  def LoadTestData(self):
    """Loads test data.

    If test-data is specified in arguments, use it. Otherwise, use default path
    DEFAULT_TEST_DATA.
    """
    if not self.args.test_data:
      self.args.test_data = os.path.join(
          os.path.dirname(__file__), DEFAULT_TEST_DATA)
    logging.debug('Using test data %r', self.args.test_data)
    with open(self.args.test_data) as f:
      self.data = yaml.load(f)

  def SetActiveDUT(self):
    """Sets active DUT.

    If active DUT is specified in arguments, use it. Otherwise, use the first
    DUT in test data.
    """
    selected_dut = None
    if self.args.dut:
      logging.info('Setting active DUT to %r.', self.args.dut)
      for dut in self.data['duts']:
        if dut['name'] == self.args.dut:
          selected_dut = dut
    else:
      selected_dut = self.data['duts'][0]
      logging.info('Using default DUT %r, which is the first DUT in test data.',
                   selected_dut['name'])
    self.fake_client_info = FakeClientInfo(selected_dut)

  def InitConnection(self):
    """Initializes a connection using proxy."""
    logging.info('Initializing an UmpireServerProxy connecting to %r',
                 self.args.server_uri)

    self.proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.args.server_uri,
        umpire_client_info=self.fake_client_info)

  def CallMethod(self):
    """Calls a method using proxy if method is specified in arguments."""
    if not self.args.method:
      return
    arguments = None
    for method in self.data['methods']:
      if method['name'] == self.args.method:
        arguments = method.get('args', None)
    if arguments:
      logging.info('Calling method %r with args %r through proxy.',
                   self.args.method, arguments)
      result = self.proxy.__getattr__(self.args.method)(*arguments)
    else:
      logging.info('Calling method %r without args through proxy.',
                   self.args.method)
      result = self.proxy.__getattr__(self.args.method)()
    logging.info('Result: %r', result)


if __name__ == '__main__':
  UmpireServerProxyCLI().Main()
