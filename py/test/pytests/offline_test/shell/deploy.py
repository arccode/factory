#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import dut as dut_module
from cros.factory.test.args import Args
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import type_utils


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

  def __init__(self, dut):
    """Constructor of ScriptBuilder.

    :type dut: cros.factory.test.dut.board.DUTBoard
    """
    self.tasks = []
    self.dut = dut

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
    self.tasks.append(self.FormatTemplate(template_file,
                                          id=next_task_id,
                                          **kargs))

  def WaitFor(self, wait_seconds):
    """Waits for `wait_seconds` seconds."""
    self._AddTask('wait_for.sh', seconds=wait_seconds)
    return self

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

  def TestShutdown(self):
    """Generate shutdown script by formatting `./shutdown.sh`."""

    self._AddTask('shutdown.sh')
    return self

  def TestThermalLoad(self):
    return self

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

  def VerifyComponent(self):
    return self

  def Build(self):
    """Generates the final script.

    The script will execute each declared tasks in the order they are declared.
    """

    tasks = '\n'.join(self.tasks)

    return self.FormatTemplate('main.sh',
                               data_root=self.dut.storage.GetDataRoot(),
                               total_tasks=len(self.tasks),
                               tasks=tasks)

  def FormatTemplate(self, template, *args, **kargs):
    """Formats template file by replacing place holders by arguments.

    Place holders in template file look like: {%name%}.

    Args:
      template: file path under py/test/pytests/offline_test/shell/
      args, kargs: arguments for str.format.
    """
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), template)

    with open(path) as f:
      template = f.read()

      # escape all braces
      template = template.replace("{", "{{")
      template = template.replace("}", "}}")

      # now {%...%} becomes {{%...%}}
      template = template.replace("{{%", "{")
      template = template.replace("%}}", "}")

      return template.format(*args, **kargs)

class DeployShellOfflineTest(unittest.TestCase):

  def setUp(self):
    self.dut = dut_module.Create()
    self.builder = ScriptBuilder(self.dut)

  def runTest(self):
    raise NotImplementedError

