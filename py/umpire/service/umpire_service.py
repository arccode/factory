# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire service base class.

Umpire service is an external application with a python class wrapper that
provides twisted process protocol. This is the base class and a global registry
for all service module.
"""


# The attributes of Twisted reactor and AttrDict object are changing
# dynamically at run time. To supress warnings, pylint: disable=E1101


import collections
import copy
import importlib
import logging
import os
import sys
import time
import uuid
from twisted.internet import protocol, reactor, defer

import factory_common  # pylint: disable=W0611
from cros.factory.schema import FixedDict, Scalar
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.utils import AttrDict, ConcentrateDeferreds


# Service package path
_SERVICE_PACKAGE = 'cros.factory.umpire.service'
# Service restart within _STARTTIME_LIMIT seconds is considered abnormal.
_STARTTIME_LIMIT = 1.2
# The maximum retries before cancel restarting external service.
_MAX_RESTART_COUNT = 3
# The maximum line of stdout and stderr messages for error logging.
_MESSAGE_LINES = 10
# Optional service config schema
_OPTIONAL_SERVICE_SCHEMA = {
    'active': Scalar('Default service state on start', bool)}
# Map service name to sys.modules.
_SERVICE_MAP = {}
# Map service name to object.
_INSTANCE_MAP = {}


# Process and service state
class State:  # pylint: disable=W0232
  INIT = 'init'
  STARTING = 'starting'
  RESTARTING = 'restarting'
  STARTED = 'started'
  STOPPING = 'stopping'
  STOPPED = 'stopped'
  ERROR = 'error'


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
    nonhash_args: list of args ignored when calculate config hash.
    pid: system process ID.
    restart_count: counts the service restarting within _STARTTIME_LIMIT.
    start_time: record external executable's start time.
    subprocess: twisted transport object to control spawned process.
    deferred_stop: deferred object that notifiies on process end.
    state: process state text string defined in State class.
    process_name: process name shortcut.
    messages: stdout and stderr messages.
    callbacks: a dict to store (callback, args, kwargs) tuples for each state.
  """

  def __init__(self, service):
    self.config = AttrDict({
        'executable': '',
        'name': str(uuid.uuid1()),
        'args': [],
        'path': os.getcwd(),
        'uid': os.getuid(),
        'gid': os.getgid(),
        'ext_args': [],
        'restart': False,
        'daemon': False})
    self.nonhash_args = []
    self.pid = None
    self.restart_count = 0
    self.service = service
    self.start_time = 0
    self.subprocess = None
    self.state = State.INIT
    self.deferred_stop = None
    self.process_name = None
    self.messages = None
    self.callbacks = collections.defaultdict(list)

  def __hash__(self):
    """Define hash and eq operator to make this class usable in hashed
    collections.
    """
    # Cannot use frozenset as config's value has list, which is not hashable
    return hash(repr(sorted(self.config.items())))

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
          args - list of command line arguments, without executalbe pathname
          path - process CWD
        optional fields:
          uid - process user id
          gid - process group id
          ext_args - extra command line arguments
          restart - boolean flag for restart on process end
          daemon - boolean flag indicating the process will detach itself

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

    for key, value in config_dict.iteritems():
      if isinstance(self.config[key], list):
        if not isinstance(value, list):
          raise ValueError('Config %s should be a list' % key)
      self.config[key] = value

    self.process_name = self.service.name + ':' + self.config.name

  def SetNonhashArgs(self, args):
    """Sets nonhash args."""
    self.nonhash_args = args

  def Start(self, restart=False):
    """Starts process.

    Args:
      restart: Indicates the process is started in a restart session.
               No need to generate new deferred object.

    Returns:
      Twisted Deferred object. If no error found, the success callback
      will be fired after short period of time. Error callback is called
      when process creating failed.

      Deferred's callback result can be any value or objects other than
      Exception instance. The start deferred returns process pid as result.

      Note that if restart is set to True, returns None instead of Deferred
      object.
    """
    def Monitor(deferred):
      """Monitors process start up.

      This timer callback checks process state. When the state looks
      good, it calls success callback and changes process state.

      Args:
        deferred: The deferred object to track process start.

      Scoped var:
        self: The process protocol object.
      """
      # Stop monitor if the process daemonized, or ended early.
      if deferred.called:
        logging.debug('%s deferred was called', self.process_name)
      elif self.state == State.RESTARTING:
        # Check the newly restart process after _STARTTIME_LIMIT.
        self._ChangeState(State.STARTING)
        reactor.callLater(_STARTTIME_LIMIT, Monitor, deferred)
      elif self.state == State.STARTING:
        self._ChangeState(State.STARTED)
        deferred.callback(self.pid)
      elif self.state == State.STOPPED:
        # When starting a daemon, the process double forks itself and exit.
        deferred.callback(self.pid)
      else:
        # The process is in unexpected state, call error handler.
        deferred.errback(self._Error(
            '%s failed to start: unexpected state %s' %
            (self.process_name, self.state)))
      # End of nested function.

    if self.state not in [State.INIT, State.RESTARTING, State.STOPPED,
                          State.ERROR]:
      return defer.fail(self._Error(
          'Can not start process %s in state %s' %
          (self.process_name, self.state)))
    self.messages = []
    logging.info('%s starting', self.process_name)
    if not (os.path.isfile(self.config.executable) and
            os.access(self.config.executable, os.X_OK)):
      return defer.fail(self._Error(
          'Executable does not exist: %s' % self.config.executable))
    args = ([self.config.executable] + self.config.args + self.config.ext_args
            + self.nonhash_args)
    self.start_time = time.time()
    self.subprocess = reactor.spawnProcess(
        self,                    # processProtocol.
        self.config.executable,  # Full program pathname.
        args,                    # Args list, including executable.
        {},                      # Env vars.
        self.config.path)        # Process CWD.
    if not (self.subprocess and self.subprocess.pid):
      if restart:
        return None
      return defer.fail(self._Error('%s creation failed' % self.process_name))
    self.pid = self.subprocess.pid

    if not restart:
      self._ChangeState(State.STARTING)
      deferred_start = defer.Deferred()
      reactor.callLater(_STARTTIME_LIMIT, Monitor, deferred_start)
      return deferred_start
    # Restart is triggered in processEnded event. Hence caller will not get.
    # a new deferred. Return None here.
    return None

  def Stop(self):
    """Stops background service.

    Returns:
      Deferred object notifying if the stopping process ends successfully or
      not.
    """
    def HandleStopResult(result):
      self._Info(str(result))
      self._ChangeState(State.STOPPED)
      return result

    def HandleStopFailure(failure):
      self._Error(repr(failure))
      return failure

    self._Info('stopping')
    self._ChangeState(State.STOPPING)

    if not self.subprocess:
      self._Info('stopped')
      self._ChangeState(State.STOPPED)
      return defer.succeed(-1)

    self._Debug('SIGTERM')
    self.transport.signalProcess('TERM')
    self.deferred_stop = defer.Deferred()
    self.deferred_stop.addCallbacks(HandleStopResult, HandleStopFailure)
    return self.deferred_stop

  def AddStateCallback(self, states, cb, *args, **kwargs):
    """Attaches the callback to state change events.

    Args:
      states: one or more State.
      cb: callback callable.
    """
    if not callable(cb):
      raise UmpireError('Not a callable when adding callback: %s' % str(cb))
    if not isinstance(states, list):
      states = [states]
    for state in states:
      self.callbacks[state].append((cb, args, kwargs))

  # Twisted process protocol callbacks.
  def connectionMade(self):
    """On process start."""
    self._Debug('connection made')

  def outReceived(self, data):
    """On stdout receive."""
    self._Log(data)
    self.messages.append(data)
    if len(self.messages) > _MESSAGE_LINES:
      self.messages.pop(0)

  def errReceived(self, data):
    """On stderr receive."""
    self._Log(data)
    self.messages.append(data)
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

  def processEnded(self, status):
    """Subprocess has been ended"""
    self.subprocess = None

    self._Info('ended')
    # If the external process daemonize itself, it detaches from parent
    # Umpire process. We can ignore the process ended event.
    if self.config.daemon:
      if isinstance(status.value, protocol.ProcessDone):
        self._Info('daemonized')
        self._ChangeState(State.STOPPED)
      else:
        if isinstance(status.value, protocol.ProcessTerminated):
          terminated = status.value
          if terminated.exitCode:
            self._Info('terminated error code %d' % terminated.exitCode)
          if terminated.signal:
            self._Info('terminated on signal %s' % terminated.signal)
        self._Error(repr(terminated))
      return

    if self.state == State.STOPPING:
      self._Info('stopped successfully')
      self._ChangeState(State.STOPPED)
      if self.deferred_stop:
        deferred_stop, self.deferred_stop = self.deferred_stop, None
        deferred_stop.callback(self.pid)
      return

    if self.config.restart:
      # Allows _MAX_RESTART_COUNT restarts within _STARTTIME_LIMIT seconds.
      self._Info('restarting')

      if time.time() - self.start_time < _STARTTIME_LIMIT:
        self.restart_count += 1
      else:
        self.restart_count = 0

      if self.restart_count >= _MAX_RESTART_COUNT:
        self._Error('respawn too fast')
      else:
        self._Info('restart count %d' % self.restart_count)
        self._ChangeState(State.RESTARTING)
        self.Start(restart=True)
      return
    # For process stoped unexpectedly (state != STOPPING) and is not allow
    # to restart. Change process state to ERROR and log the message.
    error = self._Error('ended unexpectedly. messages: \n%s' %
                        '\n'.join(self.messages))
    if self.deferred_stop:
      deferred_stop = self.deferred_stop
      self.deferred_stop = None
      deferred_stop.errback(error)

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
    for (cb, args, kwargs) in self.callbacks[state]:
      cb(*args, **kwargs)

  def _Log(self, msg):
    """Writes log messages to service handler.

    _Log() calls parent_service.log.write(). The child processes' stdout
    and stderr will be redirected to here.

    Args:
      msg: String message to write.
    """
    if self.service.log:
      self.service.log.write(msg)

  def _Debug(self, message):
    """Shortcut to logging.debug."""
    logging.debug('%s(%s) %s', self.process_name, self.pid, message)

  def _Info(self, message):
    """Shortcut to logging.info."""
    logging.info('%s(%s) %s', self.process_name, self.pid, message)

  def _Error(self, message):
    """Shortcut to logging.error.

    Returns:
      UmpireError object.
    """
    logging.error('%s(%s) %s', self.process_name, self.pid, message)
    self._ChangeState(State.ERROR)
    return UmpireError(message)


class UmpireService(object):

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
    self.module = sys.modules[full_modulename]
    _SERVICE_MAP[self.modulename] = self.module
    _INSTANCE_MAP[self.modulename] = self
    if not hasattr(self, 'name'):
      self.name = self.modulename
      if '_unittest' in self.modulename or 'test_' in self.modulename:
        self.name = self.classname

  def CreateProcesses(self, dummy_config, dummy_env):
    """Creates list of processes via config.

    Params:
      dummy_config: Umpire config dict.
      dummy_env: UmpireEnv.

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
    def HandleStartResult(results):
      logging.info('Service %s started: %s', self.name, results)
      return results

    def HandleStartFailure(failure):
      if isinstance(failure.value, defer.FirstError):
        failure = failure.value.subFailure
      logging.error('Service %s failed to start: %s',
                    self.name, failure.value)
      return failure

    # Use set() to remove duplicate processes.
    processes = set(processes)
    starting_processes = processes - self.processes
    stopping_processes = self.processes - processes
    deferreds = [p.Start() for p in starting_processes]
    deferreds.extend([p.Stop() for p in stopping_processes])
    self.processes = processes

    if deferreds:
      deferred = ConcentrateDeferreds(deferreds)
      deferred.addCallbacks(HandleStartResult, HandleStartFailure)
      return deferred

    return defer.succeed(-1)

  def Stop(self):
    """Stops all active processes."""
    def HandleStopResult(results):
      logging.info('Service %s stopped', self.name)
      return results

    def HandleStopFailure(failure):
      if isinstance(failure.value, defer.FirstError):
        failure = failure.value.subFailure
      logging.error('Service %s failed to stop: %s',
                    self.name, failure.value)
      return failure

    deferreds = [p.Stop() for p in self.processes]
    if deferreds:
      deferred = ConcentrateDeferreds(deferreds)
      deferred.addCallbacks(HandleStopResult, HandleStopFailure)
      return deferred

    return HandleStopResult(defer.succeed(-1))


def GetServiceSchemata():
  """Gets a dictionary of service configuration schemata.

  Returns:
    A schema.FixedDict items parameter for validating service schemata.
  """
  schemata = {}
  for name, module in _SERVICE_MAP.iteritems():
    items = {}
    optional_items = {}
    if hasattr(module, 'CONFIG_SCHEMA'):
      if 'items' in module.CONFIG_SCHEMA:
        items = copy.deepcopy(module.CONFIG_SCHEMA['items'])
      if 'optional_items' in module.CONFIG_SCHEMA:
        optional_items = copy.deepcopy(module.CONFIG_SCHEMA['optional_items'])
      optional_items.update(copy.deepcopy(_OPTIONAL_SERVICE_SCHEMA))
      for key in items:
        if key in optional_items:
          del items[key]
      schemata[name] = FixedDict(
          'Service schema:' + name,
          items=items,
          optional_items=optional_items)
    else:
      schemata[name] = FixedDict(
          'Service schema:' + name,
          optional_items=copy.deepcopy(_OPTIONAL_SERVICE_SCHEMA))
  logging.debug('Got service schemata: %s', str(schemata))
  return FixedDict('Service schemata', items=schemata)


def LoadServiceModule(module_name):
  """Imports service python module.

  Returns:
    Module object.

  Raises:
    ImportError: when fails to find a name.
  """
  return importlib.import_module('.' + module_name, _SERVICE_PACKAGE)


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
  return _INSTANCE_MAP.keys()


def FindServicesWithProperty(config, prop):
  """Yields service instance that has specified property.

  Args:
    config: UmpireConfig object, or config dict.
    prop: the property string to search.

  Yields:
    Service instance.
  """
  for service in config['services']:
    instance = GetServiceInstance(service)
    if instance.properties.get(prop, None):
      yield instance
