#!/usr/bin/python -u
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The RPC fuctions and classes for HWIDService."""

import argparse
import inspect
import logging  # TODO(yllin): Replace logging with testlog
import time
import uuid

from SimpleXMLRPCServer import SimpleXMLRPCServer

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service import validator
from cros.factory.hwid.v3 import builder
from cros.factory.utils import log_utils


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
      return self._checksum_updater.ReplaceChecksum(
          hwid_config.encode('utf-8')).decode('utf-8')

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
  arg_pser.add_argument(
      '--verbose',
      action='store_true',
      default=None,
      dest='verbose',
      help='for debuggin purpose, verbose debug output')
  return arg_pser.parse_args()


def main():
  args = _ParseArgs()

  log_utils.InitLogging(verbose=args.verbose)

  hwid_server = HWIDRPCServer(addr=(args.ip, args.port))
  logging.info('HWID Service serving on http://%s:%s/', args.ip, args.port)
  hwid_server.serve_forever()


if __name__ == '__main__':
  main()
