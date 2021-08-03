# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire service base class.

Umpire service is an external application with a Python class wrapper that
provides twisted process protocol. This is the base class and a global registry
for all service module.
"""

# The attributes of Twisted reactor and type_utils.AttrDict object are changing
# dynamically at run time. To suppress warnings, pylint: disable=no-member

import copy
import importlib
import inspect
import json
import logging
import os
import uuid

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet import reactor

from cros.factory.umpire import common
from cros.factory.umpire.server import utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils

# A list of all available umpire services
_SERVICE_LIST = [
    'umpire_http', 'rsync', 'shop_floor', 'instalog', 'dkps', 'multicast',
    'umpire_sync'
]
# Service package path
_SERVICE_PACKAGE = 'cros.factory.umpire.server.service'
# Service restart within _STARTTIME_LIMIT seconds is considered abnormal.
_STARTTIME_LIMIT = 1.2
# Service not terminated within _STOPTIME_LIMIT seconds would be killed.
_STOPTIME_LIMIT = 20
# The maximum retries before cancel restarting external service.
_MAX_RESTART_COUNT = 3
# The maximum line of stdout and stderr messages for error logging.
_MESSAGE_LINES = 10
# Common service config schema
_COMMON_SERVICE_SCHEMA = {
    "description": "Common service config schema",
    "type": "object",
    "properties": {
        "active": {
            "description": "Default service state on start",
            "type": "boolean"
        }
    }
}
# Map service name to module object
_SERVICE_MAP = {}
# Map service name to object.
_INSTANCE_MAP = {}


# Process and service state
State = type_utils.Enum([
    'INIT', 'STARTING', 'STARTED', 'STOPPING', 'STOPPED', 'ERROR', 'DESTRUCTING'
])


class ServiceProcess(protocol.ProcessProtocol):
  """Service process holds one twisted process protocol.

  Twisted process protocol is a controller class of external process. It
  converts standard input/output and error into callbacks. All interface
  functions are async and the callbacks can be assigned in the returned
  Deferred objects.

  Args:
    service: Umpire service object that this process belong to.

  Attributes:
    config: process configuration, check SetConfig() for detail.
    restart_count: counts the service restarting within _STARTTIME_LIMIT.
    start_time: record external executable's start time.
    subprocess: twisted transport object to control spawned process.
    deferred_stop: deferred object that notifies on process end.
    state: process state text string defined in State class.
    process_name: process name shortcut.
    messages: stdout and stderr messages.
  """

  def __init__(self, service):
    self.config = type_utils.AttrDict({
        'executable': '',
        'name': str(uuid.uuid1()),
        'args': [],
        'path': os.getcwd(),
        'uid': os.getuid(),
        'gid': os.getgid(),
        'ext_args': [],
        'env': {},
        'restart': False})
    self.restart_count = 0
    self.service = service
    self.subprocess = None
    self.state = State.INIT
    self.start_monitor = None
    self.stop_monitor = None
    self.deferred_start = None
    self.deferred_stop = None
    self.process_name = None
    self.messages = None
    # Workaround timer for reaping process.
    self._timer = None

  def __repr__(self):
    return repr(sorted(self.config.items()))

  def __str__(self):
    return self.config['name']

  def __hash__(self):
    """Define hash and eq operator to make this class usable in hashed
    collections.
    """
    # Cannot use frozenset as config's value has list, which is not hashable
    return hash(repr(self))

  def __eq__(self, other):
    if isinstance(other, ServiceProcess):
      return self.config == other.config
    return False

  def SetConfig(self, config_dict):
    """Sets process configuration.

    Sets process executable pathname, printable name, arguments, start
    up path and optional configurations.

    Args:
      config: Dict, process configuration.
        required fields:
          executable - pathname to external executable file
          name - printable name for logging
          args - list of command line arguments, without executable pathname
          path - process CWD
        optional fields:
          uid - process user id
          gid - process group id
          ext_args - extra command line arguments
          env - environment variables
          restart - boolean flag for restart on process end

    Raises:
      ValueError() on required key not found, unknown keys or value type
      mismatch.
    """
    required_keys = {'executable', 'name', 'args', 'path'}
    all_keys = set(self.config)
    config_keys = set(config_dict)

    if not required_keys.issubset(config_keys):
      raise ValueError('Required config keys not found: %s' %
                       ','.join(required_keys - config_keys))

    if not config_keys.issubset(all_keys):
      raise ValueError('Found unknown config keys: %s' %
                       ','.join(config_keys - all_keys))

    for key, value in config_dict.items():
      if isinstance(self.config[key], list):
        if not isinstance(value, list):
          raise ValueError('Config %s should be a list' % key)
      self.config[key] = value

    self.process_name = self.service.name + ':' + self.config.name

  def CancelAllMonitors(self):
    if self.start_monitor is not None:
      if self.start_monitor.active():
        self.start_monitor.cancel()
      self.start_monitor = None
    if self.stop_monitor is not None:
      if self.stop_monitor.active():
        self.stop_monitor.cancel()
      self.stop_monitor = None

  def Start(self):
    """Starts process.

    Returns:
      Twisted Deferred object. If no error found, the success callback
      will be fired after short period of time. Error callback is called
      when process creation failed.

      Deferred's callback result can be any value or objects other than
      Exception instance. The start deferred returns process pid as result.
    """
    if self.state not in [State.INIT, State.STOPPED, State.ERROR]:
      return defer.fail(self._Error(
          'Can not start process %s in state %s' %
          (self.process_name, self.state)))
    self.messages = []
    if not (os.path.isfile(self.config.executable) and
            os.access(self.config.executable, os.X_OK)):
      return defer.fail(self._Error(
          'Executable does not exist: %s' % self.config.executable))
    self.deferred_start = defer.Deferred()
    self._ChangeState(State.STARTING)
    self._SpawnProcess()
    return self.deferred_start

  def Stop(self):
    """Stops background service.

    Returns:
      Deferred object notifying if the stopping process ends successfully or
      not.
    """
    def HandleStopResult(result):
      self._ChangeState(State.STOPPED)
      return result

    def HandleStopFailure(failure):
      self._Error(repr(failure))
      return failure

    if self.state not in [State.STARTING, State.STARTED]:
      self._Info('Ignored stop process %s in state %s' %
                 (self.process_name, self.state))
      return defer.succeed(-1)

    self.CancelAllMonitors()

    self._Info('stopping')
    self._ChangeState(State.STOPPING)

    def KillChild():
      self._Info('Process %d not stopped after %f seconds, sending SIGKILL' %
                 (self.subprocess.pid, _STOPTIME_LIMIT))
      self.subprocess.signalProcess('KILL')
    self.stop_monitor = reactor.callLater(_STOPTIME_LIMIT, KillChild)

    self._Info('Sending SIGTERM to %d' % self.subprocess.pid)
    self.subprocess.signalProcess('TERM')
    self.deferred_stop = defer.Deferred()
    self.deferred_stop.addCallbacks(HandleStopResult, HandleStopFailure)
    return self.deferred_stop

  def _SpawnProcess(self):
    args = [self.config.executable] + self.config.args + self.config.ext_args
    self._Info('%s starting, executable %s args %r' %
               (self.process_name, self.config.executable, args))
    s = reactor.spawnProcess(
        self,  # processProtocol.
        self.config.executable,  # Full program pathname.
        args,  # Args list, including executable.
        self.config.env,  # Env vars.
        self.config.path,  # Process CWD.
        usePTY=True)
    self._Info('%r' % s)

  # Twisted process protocol callbacks.
  def makeConnection(self, transport):
    self._Debug('makeConnection %s' % transport)
    self.subprocess = transport
    def Started():
      self._ChangeState(State.STARTED)
      self.deferred_start.callback(self.subprocess.pid)
    self.start_monitor = reactor.callLater(_STARTTIME_LIMIT, Started)
    return protocol.ProcessProtocol.makeConnection(self, transport)

  def connectionMade(self):
    """On process start."""
    self._Debug('connection made')

  def outReceived(self, data):
    """On stdout receive."""
    self._LogData(data)
    self.messages.append(data.decode('utf-8'))
    if len(self.messages) > _MESSAGE_LINES:
      self.messages.pop(0)

  def errReceived(self, data):
    """On stderr receive."""
    self._LogData(data)
    self.messages.append(data.decode('utf-8'))
    if len(self.messages) > _MESSAGE_LINES:
      self.messages.pop(0)

  def inConnectionLost(self):
    """On stdin close."""
    self._Debug('stdin lost')

  def outConnectionLost(self):
    """On stdout close."""
    self._Debug('stdout lost')

  def errConnectionLost(self):
    """On stderr close."""
    self._Debug('stderr lost')

  def processEnded(self, reason):
    """Subprocess has been ended."""
    del reason  # Unused.
    self.subprocess = None
    self.CancelAllMonitors()

    if self.state == State.STOPPING:
      self._Info('stopped successfully')
      self._ChangeState(State.STOPPED)
      self.deferred_stop.callback(None)
      return

    if self.config.restart:
      self._Info('restarting')
      if self.state == State.STARTING:
        self.restart_count += 1
      else:
        self.deferred_start = defer.Deferred()
        self.restart_count = 0

      if self.restart_count >= _MAX_RESTART_COUNT:
        self.deferred_start.errback(self._Error('respawn too fast'))
      else:
        self._Info('restart count %d' % self.restart_count)
        self._ChangeState(State.STARTING)
        self._SpawnProcess()
      return

    # For process stopped unexpectedly (state != STOPPING) and is not allow
    # to restart. Change process state to ERROR and log the message.
    error_message = ('ended unexpectedly. messages: \n%s' %
                     '\n'.join(self.messages))
    if self.state == State.STARTING:
      self.deferred_start.errback(self._Error(error_message))
    else:
      self._Error(error_message)

  # Local helper functions.
  def _ChangeState(self, state):
    if state == self.state:
      return
    message = ('%s state change: %s --> %s' % (self.process_name,
                                               self.state, state))
    if self.state == State.ERROR:
      logging.error(message)
    else:
      logging.debug(message)
    self.state = state

  def _LogData(self, msg):
    """Writes log messages to service handler.

    _LogData() calls parent_service.log.write(). The child processes' stdout
    and stderr will be redirected to here.

    Args:
      msg: String message to write.
    """
    if self.service.log:
      self.service.log.write(msg)

  def _Log(self, level, message):
    """Shortcut to logging.log, with correct function name and line info"""
    frame = logging.currentframe()
    while frame.f_code.co_name in ['_Log', '_Debug', '_Info', '_Error']:
      frame = frame.f_back

    lineno = frame.f_lineno
    func = frame.f_code.co_name
    message = '%s(%s) %s' % (self.process_name, self.subprocess.pid
                             if self.subprocess else None, message)

    logger = logging.getLogger()
    record = logger.makeRecord(
        __name__, level, __file__, lineno, message, [], None, func)
    logger.handle(record)

  def _Debug(self, message):
    """Shortcut to logging.debug."""
    self._Log(logging.DEBUG, message)

  def _Info(self, message):
    """Shortcut to logging.info."""
    self._Log(logging.INFO, message)

  def _Error(self, message):
    """Shortcut to logging.error.

    Returns:
      UmpireError object.
    """
    self._Log(logging.ERROR, message)
    self._ChangeState(State.ERROR)
    return common.UmpireError(message)


class UmpireService:
  """Umpire service base class.

  Umpire service can configure and launch external executables. The derived
  class names, module names and instances are exported through functions.

  Attributes:
    processes: set of running process.
    log: file handle to store stderr log output.
    ext_args: extended command line args.
    enable: false to disable the service on Umpire start.
    name: service name. The default value is service module name. When
          running unittests, default service name changed to class name.
    properties: property dictionary. Indicates the capabilities and resources
                needed.

  Example:
    svc = SimpleService()
    procs = svc.CreateProcesses(umpire_config_dict)
    svc.Start(procs)
  """

  def __init__(self):
    self.processes = set()
    self.log = None
    self.enable = True
    self.properties = {}
    # Update module map.
    self.classname = self.__class__.__name__
    full_modulename = self.__class__.__module__
    self.modulename = full_modulename.split('.')[-1]
    if not hasattr(self, 'name'):
      self.name = self.modulename
      if '_unittest' in self.modulename or 'test_' in self.modulename:
        self.name = self.classname

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Params:
      umpire_config: Umpire config dict.
      env: UmpireEnv.

    Returns:
      A list of ServiceProcess.
    """
    raise NotImplementedError

  def Start(self, processes):
    """Starts a list of ServiceProcess.

    This function also stops running processes which are not needed.

    Params:
      processes: list of ServiceProcess objects.

    Returns:
      Deferred object.
    """
    def HandleFailure(failure):
      if isinstance(failure.value, defer.FirstError):
        failure = failure.value.subFailure
      logging.error('Service %s failed to start: %s',
                    self.name, failure.value)
      return failure

    def HandleStartResult(results):
      # Ignore duplicate process and add new processes into set.
      logging.info('Service %s started: %s', self.name, results)
      return results

    def HandleStopResult(result):
      del result  # Unused.
      logging.debug('starting processes %s',
                    [str(p) for p in starting_processes])
      self.processes |= starting_processes
      starting_deferreds = [p.Start() for p in starting_processes]
      starting_deferred = utils.ConcentrateDeferreds(starting_deferreds)
      return starting_deferred

    # Use set() to remove duplicate processes.
    processes = set(processes)
    starting_processes = processes - self.processes
    stopping_processes = self.processes - processes

    logging.debug('stopping processes %s', [str(p) for p in stopping_processes])
    self.processes -= stopping_processes
    stopping_deferreds = [p.Stop() for p in stopping_processes]
    stopping_deferred = utils.ConcentrateDeferreds(stopping_deferreds)

    stopping_deferred.addCallback(HandleStopResult)
    stopping_deferred.addCallbacks(HandleStartResult, HandleFailure)
    return stopping_deferred

  def Stop(self):
    """Stops all active processes."""
    def HandleStopResult(results):
      logging.info('Service %s stopped', self.name)
      return results

    def HandleStopFailure(failure):
      if isinstance(failure.value, defer.FirstError):
        failure = failure.value.subFailure
      logging.error('Service %s failed to stop: %s', self.name, failure.value)
      return failure

    deferreds = [p.Stop() for p in self.processes]
    self.processes = set()
    deferred = utils.ConcentrateDeferreds(deferreds)
    deferred.addCallbacks(HandleStopResult, HandleStopFailure)
    return deferred


def GetAllServiceSchemata():
  """Return the JSON schema of all available Umpire services.

  Returns:
    The JSON schema of all services.
  """
  for service_name in _SERVICE_LIST:
    LoadServiceModule(service_name)
  return GetServiceSchemata()


def GetServiceSchemata():
  """Return the JSON schema of Umpire services loaded in _SERVICE_MAP.

  Returns:
    The JSON schema of field 'service' in Umpire config.
  """
  properties = {}
  for name, module in _SERVICE_MAP.items():
    module_path = os.path.dirname(os.path.realpath(module.__file__))
    config_path = os.path.join(module_path, "%s_config.schema.json" % name)
    properties[name] = copy.deepcopy(_COMMON_SERVICE_SCHEMA)
    try:
      properties[name]["properties"].update(copy.deepcopy(
          json.loads(file_utils.ReadFile(config_path))))
    except Exception:
      pass
  schemata = {
      "$schema": "http://json-schema.org/draft-04/schema#",
      "description": "Umpire service schemata",
      "type": "object",
      "properties": properties,
      "additionalProperties": False
  }
  return schemata


def LoadServiceModule(module_name):
  """Imports service Python module, populate _SERVICE_MAP and _INSTANCE_MAP.

  Returns:
    Module object.

  Raises:
    ImportError: when fails to find a name.
  """
  module = importlib.import_module('.' + module_name, _SERVICE_PACKAGE)
  for unused_obj_name, obj in inspect.getmembers(module):
    if inspect.isclass(obj) and issubclass(obj, UmpireService):
      _SERVICE_MAP[module_name] = module
      if module_name not in _INSTANCE_MAP:
        _INSTANCE_MAP[module_name] = obj()
  return module


def GetServiceInstance(module_name):
  """Gets service object.

  Returns:
    Service instance.

  Raises:
    KeyError: when module name does not exist.
  """
  return _INSTANCE_MAP[module_name]


def GetAllServiceNames():
  """Gets all service names loaded.

  Returns:
    List of service name strings.
  """
  return list(_INSTANCE_MAP)
