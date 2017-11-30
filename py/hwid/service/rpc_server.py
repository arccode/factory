#!/usr/bin/python -u
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The RPC fuctions and classes for HWIDService."""

import argparse
import inspect
import logging  # TODO(yllin): Replace logging with testlog
from multiprocessing.connection import Client
import sys
import threading
import time
import uuid

from SimpleXMLRPCServer import SimpleXMLRPCServer

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.common import Command
from cros.factory.hwid.service.common import CreateResponse
from cros.factory.hwid.service.common import InitLogger
from cros.factory.hwid.service import validator
from cros.factory.hwid.v3 import builder
from cros.factory.utils import file_utils


def DecorateAllMethods(decorator):
  """The class decorator that decorates all the public methods."""

  def _Decorate(cls):
    for func_name, func in inspect.getmembers(cls, inspect.ismethod):
      if not func_name.startswith('_'):
        setattr(cls, func_name, decorator(func))
    return cls

  return _Decorate


# TODO(yllin): Add performance profiling test.
def _LogRPC(method):
  """A decorator that logs the rpc"""

  def _LogRPCFunction(*args, **kwargs):
    rpc_unique_id = uuid.uuid4()
    t1 = time.time()
    rpc_return = method(*args, **kwargs)
    t2 = time.time()
    logging.info({
        'uuid': rpc_unique_id,
        'rpc': method.__name__,
        'date': t1,
        'delta_time': t2 - t1,
        'args': args,
        'kwargs': kwargs,
        'return': rpc_return
    })
    return rpc_return

  return _LogRPCFunction


def _RPCReturn(method):
  """A decorator that creates rpc returning dict."""

  def _CreateRPCReturn(*args, **kwargs):
    success, ret = method(*args, **kwargs)
    return {'success': bool(success), 'ret': unicode(ret) if ret else None}

  return _CreateRPCReturn


class HWIDRPCServer(SimpleXMLRPCServer):
  """The XMLRPC server for HWID Service.

  HWID Service provides API for validating and updating checksum for the new
  HWID config and returning error messages if validating failed.
  """

  def __init__(self, addr):
    """Constructor.

    Args:
      addr: A (string, int) tuple where the server serves on.
    """
    SimpleXMLRPCServer.__init__(
        self, addr=addr, logRequests=True, allow_none=True, encoding='UTF-8')
    self.register_instance(HWIDRPCInstance())
    self.register_introspection_functions()


@DecorateAllMethods(_LogRPC)
@DecorateAllMethods(_RPCReturn)
class HWIDRPCInstance(object):
  """HWIDServer XMLRPC instance."""

  def __init__(self):
    """Constructor.

    Attributes:
      _checksum_updater: Updates the HWID checksum.
      _hwid_validator: A Validator object for validating HWID config.
    """
    self._checksum_updater = builder.ChecksumUpdater()
    assert self._checksum_updater is not None

  def ValidateConfig(self, hwid_config):
    """A RPC function for validating HWID config including checksum check.

    The function does a strict validating (i.e. including checksum validating).

    Args:
      hwid_config: A HWID config in unicode.

    Retruns:
      A dict containing 'success' and 'ret' keys, where 'success' is a bool to
      indicate the config is validate or invalidated; 'ret' is a string that
      shows failure message, and is None on HWID validated.
      e.g. {'success': True, 'ret': None},
           {'success': False, 'ret': 'ValidationError:...'}
    """
    try:
      validator.Validate(hwid_config)
      return True, None
    except validator.ValidationError as e:
      return False, 'ValidationError: %s' % e.message
    except Exception as e:
      return False, 'UnknownError: %s' % e.message

  def ValidateConfigAndUpdateChecksum(self, new_hwid_config, old_hwid_config):
    """A RPC function for validating and updating new HWID config

    This function first update the checksum of new_hwid_config ,and then
    strictly validate the new_hwid_config to make sure it is correct. At last,
    it validate the change of new_hwid_config and returns it with the new
    checksum.

    Args:
      new_hwid_config: The new hwid config in unicode (without checksum).
      old_hwid_config: The old hwid config in unicode (w/o checksum).

    Retruns:
      A dict containing 'success' and 'ret' keys, where 'success' is a bool to
      indicate the config is validate or invalidated; 'ret' is a string that
      shows HWID config with updated checksum on success, and failure message on
      failure.
      e.g. {'success': False, 'ret': 'UnknownError: ...'},
           {'success': True, 'ret': '...###### BEGIN CHECKSUM BLOCK....'}

    """

    def _UpdateChecksum(hwid_config):
      with file_utils.UnopenedTemporaryFile() as filename:
        with open(filename, 'w') as f:
          f.write(hwid_config.encode('utf-8'))
        self._checksum_updater(filename)
        with open(filename, 'r') as f:
          return f.read().decode('utf-8')

    try:
      updated_hwid_config = _UpdateChecksum(new_hwid_config)
    except Exception as e:
      return False, 'ChecksumUpdatingError: %s' % e.message

    try:
      validator.ValidateChange(updated_hwid_config, old_hwid_config)
      return True, updated_hwid_config
    except validator.ValidationError as e:
      return False, 'ValidationError: %s' % e.message
    except Exception as e:
      return False, 'UnknownError: %s' % e.message


class HWIDService(object):
  """The HWIDService class.

  HWIDService provides HWID related RPC functions running on Google Container
  Engine (GKE). The functions currently we only provide validating and checksum
  updating, and we are going to provide more and more HWID functions in the near
  future.

  The ServiceManager controls the lifetime of the HWIDService. It creates
  the HWIDService by invoking a process and destroys it by sending Terminate
  request via _cmd_conn.

  Properties:
    _server: instance of HWIDRPCServer
    _standalone: running in standalone mode (for testing)
    _server_thread: the thread instance running HWIDRPCServer
    _cmd_conn: a socket connection between ServiceManager and HWIDService
  """

  def __init__(self, address, standalone, cmd_conn_address=None, authkey=None):
    """Constuctor of HWIDService.

    Args:
      address: A tuple of (ip, port) for HWID RPC Server
      standalone: A bool for whether running in a standalone mode
      cmd_conn_address: A tuple of (ip, port) for cmd_conn
      authkey: Authkey of cmd_conn
    """
    super(HWIDService, self).__init__()
    self._server = HWIDRPCServer(address)
    self._standalone = standalone

    if self._standalone is True:
      self._server_thread = None
      self._cmd_conn = None
    else:
      self._server_thread = threading.Thread(target=self._server.serve_forever)
      self._server_thread.setDaemon(True)
      self._cmd_conn = Client(cmd_conn_address, authkey=authkey)

  def RunForever(self):
    """Runs HWIDService forever until ShutDown or received command Terminate."""
    if self._standalone is True:
      return self._server.serve_forever()

    self._server_thread.start()

    while True:
      request = self._cmd_conn.recv()
      if request['command'] == Command.TERMINATE:
        self._HandleTerminate(request)
        sys.exit()
      else:
        response = Command.Response(
            request=request, success=False, msg='Unknown command')
        self._cmd_conn.send(response)

  def ShutDown(self):
    """Shut down the HWIDServer."""
    self._server.shutdown()

  def _HandleTerminate(self, request):
    try:
      # Make sure the service terminated properly so that everything is logged.
      self.ShutDown()
      self._server_thread.join()
      response = CreateResponse(
          request=request, success=True, msg='HWID Service Terminated.')
    except Exception as e:
      response = CreateResponse(request=request, success=False, msg=e.message)
    finally:
      self._cmd_conn.send(response)
      self._cmd_conn.close()


def _ParseArgs():
  arg_pser = argparse.ArgumentParser(description='Factory HWID Service')

  # HWID Service options.
  arg_pser.add_argument(
      '--ip',
      type=str,
      dest='ip',
      default='0.0.0.0',
      help='bind HWID Service to IP; defaults to 0.0.0.0')
  arg_pser.add_argument(
      '--port',
      type=int,
      dest='port',
      default=8181,
      help='bind HWID Service to port; defaults to 8181')

  # ServiceManager message connection options.
  arg_pser.add_argument(
      '--sm-ip',
      type=str,
      dest='sm_ip',
      help='ServiceManager command listening ip')
  arg_pser.add_argument(
      '--sm-port',
      type=int,
      dest='sm_port',
      help='ServiceManager command listening port')
  arg_pser.add_argument(
      '--authkey',
      type=str,
      dest='authkey',
      default=None,
      help='auth key of Service Manager command connection')
  arg_pser.add_argument(
      '--standalone',
      action='store_true',
      default=False,
      dest='standalone',
      help='for debuggin purpose, runs without ServiceManager')
  arg_pser.add_argument(
      '--verbose',
      action='store_true',
      default=None,
      dest='verbose',
      help='for debuggin purpose, verbose debug output')
  return arg_pser.parse_args()


def main():
  args = _ParseArgs()

  InitLogger(args.verbose)
  service = HWIDService(
      address=(args.ip, args.port),
      cmd_conn_address=(args.sm_ip, args.sm_port),
      authkey=args.authkey,
      standalone=args.standalone)
  service.RunForever()


if __name__ == '__main__':
  main()
