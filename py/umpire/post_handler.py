# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=E1101

"""Umpire HTTP POST upload handlers

Handlers should be static methods, returned a tuple
  (HTTP_STATUS, HTTP_CONTENT_DATA)
where HTTP_CONTENT_DATA can be anything JSON-serializable
URL:
  http://umpire_server_address:umpire_webapp_port/upload/<handler_name>

Internal handlers accept every post fields as a list, even if there's only one
value in that field. **kwargs cannot guarantee order of args on keys, but order
of same field will be kept in list.

Files will be treated as a string contains its content, without any other
information.

Note that only functions decorated by @internal_handler are treated as handler.

External handlers are located in {server_toolkit}/usr/local/factory/bin/.
Args will be flatten into a list of string, field name follows values.
Fields named 'file' or with prefix 'file-' will be saved as named temp file,
passing filename instead of file body.
"""

import logging
import os
import tempfile

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.internet import threads
from twisted.web import http

import factory_common  # pylint: disable=W0611

env = [{}]
_post_handlers = {}
EXTERNAL = 'RunExternalHandler'


def InternalHandler(func):
  """Decorator of internal handler.

  Register a function as a internal handler. Only registered functions can be
  called by POST requests.
  """
  _post_handlers[func.__name__] = func
  return func


def GetPostHandler(name):
  return _post_handlers.get(name, None)


def SetEnv(environ):
  env[0] = environ


class HandlerError(Exception):
  pass


@InternalHandler
def Echo(**kwargs):
  """Echo received args.

  Raise:
    HandlerError if args contains 'exception'.
  """
  if 'exception' in kwargs:
    raise HandlerError()
  ret = {}
  for k, v in kwargs.iteritems():
    value = repr(v)
    if len(value) > 128:
      value = value[:128] + '......'
    ret[k] = value
  return defer.succeed((http.OK, ret))


class ExternalProcessProtocol(protocol.ProcessProtocol):
  """Twisted process event handler.

  It records output and exit code, invokes callback to handle response on
  process exit.
  """

  def __init__(self, handler, files=None):
    """Initializes an process event handler.
    Args:
      handler: Path of executable.
      files: Reference of temporary files.
    """
    self.stdout = []
    self.stderr = []
    self.exit_code = -1
    self.handler = handler
    # Keep references of files to prevent temp_file be garbage collected and
    # closed automatically.
    self.files = files
    self.ended = False
    # spawnProcess() won't wait for execution, so make a new empty Deferred
    # to register callback, then let processEnded event invokes it manually.
    self.deferred = defer.Deferred()

  def outReceived(self, data):
    logging.info('stdout: %s', data)
    self.stdout.append(data)

  def errReceived(self, data):
    logging.info('stderr: %s', data)
    self.stderr.append(data)

  def processEnded(self, status):
    logging.info('.. process end with %s', status)
    self.exit_code = status.value.exitCode

    content = {}
    content['stdout'] = ''.join(self.stdout)
    content['stderr'] = ''.join(self.stderr)
    content['exit_code'] = self.exit_code
    logging.info('POST Handler: external executable %s returns exit code %s',
                 self.handler, content['exit_code'])

    status = http.OK
    if content['exit_code'] != 0:
      status = http.INTERNAL_SERVER_ERROR

    self.deferred.callback((status, content))


@InternalHandler
def RunExternalHandler(handler, **kwargs):
  """Spawn external handler to handle request.

  Note that we only guarantee argument order of same field, NOT between fields.

  Returns a deferred object
  """

  # Twisted default saved args using list, even if there's only 1 value
  # in that field.
  if isinstance(handler, list):
    handler = handler[0]
  handler_path = str(_GetFullHandlerPath(handler))

  # To prevent temp files to be recycled before Spawn(), keep references.
  files = {}
  proto = ExternalProcessProtocol(handler_path, files)

  def _Spawn(args_list):
    args = [handler_path]
    args.extend(args_list)
    reactor.spawnProcess(proto, handler_path, args)

  def _ReturnErrorResponse(fail):
    # TODO: When spawnProcess() failed (ex. file not found) it won't raise
    # exception, return non-zero exit code and write error message to stderr
    # instead.
    # errback cannot catch it. Maybe need other ways to recognize them, or
    # just ignore this problem, treats it as execution error?
    logging.info('POST Handler: SpawnProcess() causes error %s', fail)
    proto.deferred.errback((http.INTERNAL_SERVER_ERROR, {'exception': repr(fail)}))

  # Defer function that contains file IO, then spawn process, but don't return.
  d = threads.deferToThread(_TranslateArgs, kwargs, files)
  d.addCallback(_Spawn)
  d.addErrback(_ReturnErrorResponse)

  return proto.deferred


def _TranslateArgs(args, files):
  """Translate arguments to strings for Spawn external handler.

  It unpacks args into a string list for Spawn(), saving files in tempfile
  and replaces them with name of tempfile.
  """
  ret = []
  for k in args.keys():
    # Check if it's file. We received file body as string from Twisted,
    # unable to recognize with other field, so we recognize field name.
    ret.append(k)
    if k == 'file' or k.startswith('file-'):
      file_list = []
      for fb in args[k]:
        temp_file = tempfile.NamedTemporaryFile()
        temp_file.write(fb)
        temp_file.flush()
        file_list.append(temp_file)
        ret.append(temp_file.name)
      files[k] = file_list
    else:
      ret.extend(args[k])
  return ret


def _GetFullHandlerPath(handler_name):
  return os.path.join(env[0].server_toolkits_dir, 'usr/local/factory/bin',
                      handler_name)

