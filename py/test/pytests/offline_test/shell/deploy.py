#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import pipes
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import dut as dut_module
from cros.factory.test.dut.boards import android
from cros.factory.test.args import Arg
from cros.factory.test.args import Args
from cros.factory.test.pytests.offline_test.shell import common
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import type_utils


def _FormatTemplate(template, *args, **kargs):
  """Formats template file by replacing place holders by arguments.

  Place holders in template file look like: {%name%}.

  Args:
    template: file path under py/test/pytests/offline_test/shell/
    args, kargs: arguments for str.format.
  """
  path = os.path.join(common.CURRENT_DIR, template)

  with open(path) as f:
    template = f.read()

    # escape all braces
    template = template.replace("{", "{{")
    template = template.replace("}", "}}")

    # now {%...%} becomes {{%...%}}
    template = template.replace("{{%", "{")
    template = template.replace("%}}", "}")

    return template.format(*args, **kargs)


class FunctionMapper(object):
  """A decorator class for registering alias names for functions.

  Example::
      mapper = FunctionMapper()
      @mapper.Register('foo')
      def func(a, b, c):
        ...

      mapper.CallFunction('foo', 4, 5, 6)
  """
  def __init__(self):
    self._FUNCTION_MAP = {}

  def Register(self, alias_name):
    if alias_name in self._FUNCTION_MAP:
      logging.warn('`%s` already registered, overriding old value', alias_name)
    def wrapper(func):
      self._FUNCTION_MAP[alias_name] = func
      return func
    return wrapper

  def CallFunction(self, alias_name, *args, **kargs):
    """Call a function registered with alias name `alias_name`.

    The function registered with name `alias_name` will be called with keyword
    arguments `kargs` and bind to `obj`.

    Args:
      alias_name: a str, the registered name of the function.
      obj: a object which the function should bind to.
      kargs: additional arguments for the function.
    """
    return self._FUNCTION_MAP[alias_name](*args, **kargs)


class ScriptBuilder(object):
  """Builder class for shell offline test.

  Example::

    builder = ScriptBuilder(dut.Create())
    builder.TestStressApp(0.5, 20, True)
    builder.WaitFor(10)
    builder.TestShutdown()
    for unused_i in xrange(10):
      builder.TestStressApp(0.5, 20, True)
    print builder.Build()
  """

  ShellTestCase = FunctionMapper()

  def __init__(self, dut, data_root):
    """Constructor of ScriptBuilder.

    Args:
      :type dut: cros.factory.test.dut.board.DUTBoard
      dut: used to get data from DUT.

      :type data_root: str
      data_root: where to store the state of offline testing.
    """
    self.tasks = []
    self.dut = dut
    self.data_root = data_root

  @type_utils.LazyProperty
  def cpu_count(self):
    return self.dut.info.cpu_count or 1

  @type_utils.LazyProperty
  def memory_total_kb(self):
    return self.dut.info.memory_total_kb or (100 * 1024)

  def Clear(self):
    self.tasks = []

  def _AddTask(self, template_file, **kargs):
    next_task_id = len(self.tasks) + 1  # task index is 1 based.
    self.tasks.append(_FormatTemplate(template_file,
                                      id=next_task_id,
                                      **kargs))

  def Build(self):
    """Generates the final script.

    The script will execute each declared tasks in the order they are declared.
    """

    tasks = '\n'.join(self.tasks)

    return _FormatTemplate('main.sh',
                           data_root=self.data_root,
                           total_tasks=len(self.tasks),
                           tasks=tasks)

  def AddShellTestCase(self, test_name, **kargs):
    self.ShellTestCase.CallFunction(test_name, self, **kargs)
    return self

  def AddPythonTestCase(self, pytest_name, **kargs):
    """Generates a test case using `factory.par run_pytest`.

    Push factory.par to DUT, and the shell script will use factory.par to run
    `cros.factory.test.pytests.<pytest_name>` with arguments `kargs`.
    The `board_class` of `dut_options` will be the same with `self.dut`, and
    `link_class` will be `LocalLink`.

    The pytest is not guaranteed to be able to run on DUT, since it might
    requires Goofy, or it requires Chrome OS envrionment.
    """

    archive = deploy_utils.FactoryPythonArchive(self.dut)
    archive.PushFactoryPar()

    dut_options = {
        'board_class': self.dut.__class__.__name__,
        'link_class': 'LocalLink'}

    cmd = archive.DryRun(['run_pytest', '--args', repr(kargs), '--dut-options',
                          repr(dut_options), '--no-use-goofy', pytest_name])
    cmd = ' '.join(map(pipes.quote, cmd))

    self._AddTask('call_factory_par.sh', cmd=cmd)
    return self

  @ShellTestCase.Register('wait_for')
  def WaitFor(self, wait_seconds):
    """Waits for `wait_seconds` seconds."""
    self._AddTask('wait_for.sh', seconds=wait_seconds)
    return self

  @ShellTestCase.Register('stressapptest')
  def TestStressApp(self, memory_ratio, seconds, disk_thread):
    """Generate stressapptest script by formatting `./stressapptest.sh`."""

    if disk_thread:
      disk_thread = ('-f "${tmpdir}/sat.disk_thread.a" '
                     '-f "${tmpdir}/sat.disk_thread.b"')
    else:
      disk_thread = ''

    mem_usage = max(int(self.memory_total_kb * memory_ratio / 1024), 32)

    self._AddTask('stressapptest.sh', cpu_count=self.cpu_count,
                  mem_usage=mem_usage, seconds=seconds, disk_thread=disk_thread)

    return self

  @ShellTestCase.Register('shutdown')
  def TestShutdown(self):
    """Generate shutdown script by formatting `./shutdown.sh`."""

    self._AddTask('shutdown.sh')
    return self

  @ShellTestCase.Register('thermal_load')
  def TestThermalLoad(self):
    return self

  @ShellTestCase.Register('bad_blocks')
  def TestBadBlocks(self, **kargs):
    """Generates the bad blocks test.

    Args:
      Please refer to `cros.factory.test.pytests.bad_blocks.BadBlocksTest.ARGS`
      for the argument list.
    """
    module = pytest_utils.LoadPytestModule('bad_blocks')
    test = module.BadBlocksTest()
    test.dut = self.dut
    test.args = Args(*test.ARGS).Parse(kargs)

    test.CheckArgs()
    params = test.DetermineParameters()
    self._AddTask('bad_blocks.sh',
                  is_file=('true' if test.args.mode == 'file' else 'false'),
                  **params._asdict())
    return self


class DeployShellOfflineTest(unittest.TestCase):
  """A factory test to deploy shell offline test."""

  NEXT_ACTION = type_utils.Enum(['REBOOT', 'POWEROFF', 'START_TEST', 'NOP'])

  ARGS = [
      Arg('test_spec', list,
          'Please refer to _`py/test/pytests/offline_test/shell/README`.'),
      Arg('next_action', NEXT_ACTION,
          ('What to do after tests are deployed (One of %s)' % NEXT_ACTION)),
      Arg('start_up_service', bool, 'Do you want to run the tests on start up?',
          default=True, optional=True)]

  def setUp(self):
    self.dut = dut_module.Create()
    self.data_root = common.DataRoot(self.dut)
    self.test_script_path = common.TestScriptPath(self.dut)
    self.builder = ScriptBuilder(self.dut, self.data_root)

  def _MakeChromeOsStartUpApp(self, starter_path):
    # Chrome OS images will execute '/usr/local/factory/init/startup' if
    # file '/usr/local/factory/enabled' exists.
    # so if we create the enabled file and make a symbolic link for our starter,
    # our script will be executed on start up.
    self.dut.CheckCall(['mkdir', '-p', '/usr/local/factory/init'])
    self.dut.CheckCall(['touch', '/usr/local/factory/enabled'])
    self.dut.CheckCall(['ln', '-sf', starter_path,
                        '/usr/local/factory/init/startup'])

  def _MakeStartUpApp(self, starter_path):
    if isinstance(self.dut, android.AndroidBoard):
      # TODO(stimim): support Android init
      raise NotImplementedError
    else:
      self._MakeChromeOsStartUpApp(starter_path)

  def runTest(self):
    script_dir = common.ScriptRoot(self.dut)

    # make sure script_dir is writable
    if not self.dut.storage.Remount(script_dir):
      raise common.OfflineTestError(
          'failed to make dut:%s writable' % script_dir)
    # create script_dir
    self.dut.Call(['rm', '-rf', script_dir])
    self.dut.CheckCall(['mkdir', '-p', script_dir])

    # make sure data_root is writable
    if not self.dut.storage.Remount(self.data_root):
      raise common.OfflineTestError(
          'failed to make dut:%s writable' % self.data_root)
    # create data_root
    self.dut.Call(['rm', '-rf', self.data_root])
    self.dut.CheckCall(['mkdir', '-p', self.data_root])

    for spec in self.args.test_spec:
      dargs = spec.get('dargs', {})
      if 'shtest_name' in spec:
        self.builder.AddShellTestCase(spec['shtest_name'], **dargs)
      elif 'pytest_name' in spec:
        self.builder.AddPythonTestCase(spec['pytest_name'], **dargs)
      else:
        raise ValueError('You must specify one of `shtest_name` and '
                         '`pytest_name`')

    # push generated script
    self.dut.WriteFile(self.test_script_path, self.builder.Build())
    self.dut.Call(['chmod', '+x', self.test_script_path])

    starter_path = self.dut.path.join(script_dir, 'starter.sh')
    # push starter script
    self.dut.WriteFile(starter_path,
                       _FormatTemplate('starter.sh', data_root=self.data_root,
                                       test_script_path=self.test_script_path))
    self.dut.Call(['chmod', '+x', starter_path])

    if self.args.start_up_service:
      self._MakeStartUpApp(starter_path)

    if self.args.next_action == self.NEXT_ACTION.POWEROFF:
      self.dut.Call(['shutdown', 'now'])
    elif self.args.next_action == self.NEXT_ACTION.REBOOT:
      self.dut.Call(['shutdown', 'reboot'])
    elif self.args.next_action == self.NEXT_ACTION.START_TEST:
      self.dut.Call(['sh', self.test_script_path])
    elif self.args.next_action == self.NEXT_ACTION.NOP:
      pass
    else:
      raise ValueError('`next_action` must be one of %s (it is %s)' %
                       (self.NEXT_ACTION, self.args.next_action))
