#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Command-line interface for miscellaneous factory actions.

Run "factory --help" for more info and a list of subcommands.

To add a subcommand, just add a new Subcommand subclass to this file.
"""


import argparse
import inspect
import logging
import socket
import sys
import time
import yaml
from setproctitle import setproctitle

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test.factory import TestState
from cros.factory.test.test_lists import test_lists
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


class Subcommand(object):
  """A 'factory' subcommand.

  Properties:
    name: The name of the command (set by the subclass).
    help: Help text for the command (set by the subclass).
    parser: The ArgumentParser object.
    subparser: The subparser object created with parser.add_subparsers.
    subparsers: A collection of all subparsers.
    args: The parsed arguments.
  """
  name = None  # Overridden by subclass
  help = None  # Overridden by subclass

  parser = None
  args = None
  subparser = None
  subparsers = None

  def Init(self):
    """Initializes the subparser.

    May be implemented the subclass, which may use "self.subparser" to
    refer to the subparser object.
    """
    pass

  def Run(self):
    """Runs the command.

    Must be implemented by the subclass.
    """
    raise NotImplementedError()


class HelpCommand(Subcommand):
  name = 'help'
  help = 'Get help on COMMAND'

  def Init(self):
    self.subparser.add_argument('command', metavar='COMMAND', nargs='?')

  def Run(self):
    if self.args.command:
      choice = self.subparsers.choices.get(self.args.command)
      if not choice:
        sys.exit('Unknown subcommand %r' % self.args.command)
      choice.print_help()
    else:
      self.parser.print_help()


class RunCommand(Subcommand):
  name = 'run'
  help = 'Run a test'

  def Init(self):
    self.subparser.add_argument(
        'id', metavar='ID',
        help='ID of the test to run')

  def Run(self):
    factory.get_state_instance().RunTest(self.args.id)
    print 'Running test %s' % self.args.id


class WaitCommand(Subcommand):
  name = 'wait'
  help = ('Wait for all tests to finish running, displaying status as testing '
          'progresses')

  def Init(self):
    self.subparser.add_argument(
        '--poll-interval', type=int, default=1,
        help='Poll interval in seconds')

  def Run(self):
    # Dict mapping test path -> test information.
    last_test_dict = None

    while True:
      tests = factory.get_state_instance().GetTests()
      test_dict = {}
      for t in tests:
        # Don't bother showing parent nodes.
        if t['parent']:
          continue
        if last_test_dict is None:
          # First time; just print active tests
          if t['status'] == TestState.ACTIVE:
            print '%s: %s' % (t['path'], t['status'])
        else:
          # Show any tests with changed statuses.
          if t['status'] != last_test_dict[t['path']]['status']:
            sys.stdout.write('%s: %s' % (t['path'], t['status']))
            if t['status'] == TestState.FAILED:
              sys.stdout.write(' (%r)' % str(t['error_msg']))
            sys.stdout.write('\n')

        test_dict[t['path']] = t

      # Save the test information for next time.
      last_test_dict = test_dict
      sys.stdout.flush()
      if not any(t['pending'] for t in tests):
        # All done!  Bail.
        print 'done'
        break
      # Wait one second and poll again
      time.sleep(1)


class TestsCommand(Subcommand):
  name = 'tests'
  help = 'Show information about tests'

  def Init(self):
    self.subparser.add_argument(
        '--interesting', '-i', action='store_true',
        help=('Show only information "interesting" tests '
              '(tests that are not untested or passed'))
    self.subparser.add_argument(
        '--status', '-s', action='store_true',
        help='Include information about test status')
    self.subparser.add_argument(
        '--yaml', action='store_true',
        help='Show lots of information in YAML format')

  def Run(self):
    goofy = factory.get_state_instance()
    tests = goofy.GetTests()

    # Ignore parents
    tests = [x for x in tests if not x.get('parent')]

    if self.args.interesting:
      tests = [
          x for x in tests if x['status'] in [
              TestState.ACTIVE, TestState.FAILED]]

    if self.args.yaml:
      print yaml.safe_dump(tests)
    elif self.args.status:
      for t in tests:
        sys.stdout.write(t['path'])
        if t['status'] != TestState.UNTESTED:
          sys.stdout.write(': %s' % t['status'])
        if t['error_msg']:
          sys.stdout.write(': %r' % str(t['error_msg']))
        sys.stdout.write('\n')
    else:
      for t in tests:
        print t['path']


class ClearCommand(Subcommand):
  name = 'clear'
  help = 'Stop all tests and clear test state'

  def Run(self):
    factory.get_state_instance().ClearState()


class StopCommand(Subcommand):
  name = 'stop'
  help = 'Stop all tests'

  def Run(self):
    factory.get_state_instance().StopTest()


class DumpTestListCommand(Subcommand):
  name = 'dump-test-list'
  help = 'Dump a test list in YAML format'

  def Init(self):
    self.subparser.add_argument(
        'id', metavar='ID', help='ID of test list to dump')

  def Run(self):
    test_list = test_lists.BuildTestList(self.args.id)
    if isinstance(test_list, test_lists.OldStyleTestList):
      test_list = test_list.Load()
    test_lists.YamlDumpTestListDestructive(test_list, sys.stdout)


class TestListCommand(Subcommand):
  name = 'test-list'
  help = 'Set or get the active test list, and/or list all test lists'

  TIMEOUT_SECS = 60
  POLL_INTERVAL_SECS = 0.5

  def Init(self):
    self.subparser.add_argument(
        'id', metavar='ID', nargs='?',
        help=('ID of test list to activate (run '
              '"factory test-list --list" to see all available IDs)'))
    self.subparser.add_argument(
        '--list', action='store_true',
        help='List all available test lists')
    self.subparser.add_argument(
        '--restart', action='store_true',
        help='Restart goofy and wait for new test list to come up')
    self.subparser.add_argument(
        '--clear-all', '-a', action='store_true',
        help='If restarting goofy, clear all state (like factory_restart -a)')

  def Run(self):
    if self.args.id:
      all_test_lists = test_lists.BuildAllTestLists()

      if self.args.id not in all_test_lists:
        sys.exit('Unknown test list ID %r (use "factory test-lists" to see '
                 'available test lists' % self.args.id)
      test_lists.SetActiveTestList(self.args.id)
      print 'Set active test list to %s (wrote %r to %s)' % (
          self.args.id, self.args.id, test_lists.ACTIVE_PATH)
      sys.stdout.flush()
    else:
      print test_lists.GetActiveTestListId()

    if self.args.list:
      all_test_lists = test_lists.BuildAllTestLists()
      active_id = test_lists.GetActiveTestListId()

      line_format = '%-8s %-20s %s'
      print line_format % ('ACTIVE?', 'ID', 'PATH')

      for k, v in sorted(all_test_lists.items()):
        is_active = '(active)' if k == active_id else ''
        path = (v.path if isinstance(v, test_lists.OldStyleTestList)
                else v.source_path)
        print line_format % (is_active, k, path)

    if self.args.restart:
      goofy = factory.get_state_instance()

      # Get goofy's current UUID
      try:
        uuid = goofy.GetGoofyStatus()['uuid']
      except socket.error:
        logging.info("goofy is not up")
      except:  # pylint: disable=W0702
        logging.exception('Unable to get goofy status; assuming it is down')
        uuid = None

      # Set the proc title so factory_restart won't kill us.
      setproctitle('factory set-active-test-list')

      # Restart goofy, clearing its state
      Spawn(['factory_restart'] +
            (['-a'] if self.args.clear_all else []),
            check_call=True, log=True)

      # Wait for goofy to come up with a different UUID
      start = time.time()

      last_status_summary = None

      while True:
        try:
          status = goofy.GetGoofyStatus()
          status_summary = str(status)
          if status['uuid'] == uuid:
            # goofy hasn't shut down yet
            continue
          if status['status'] == 'RUNNING':
            # All good
            logging.info(status_summary)
            logging.info('goofy is up')
            if status['test_list_id'] != self.args.id:
              # Shouldn't ever happen
              sys.exit('goofy came up with wrong test list %r' %
                       status['test_list_id'])
            return
          if status['status'] not in ['UNINITIALIZED', 'INITIALIZING']:
            # This means it's never going to come up.
            sys.exit('goofy failed to come up; status is %r',
                     status['status'])
        except:  # pylint: disable=W0702
          status_summary = 'Exception: %s' % utils.FormatExceptionOnly()
          if 'Connection refused' in status_summary:
            # Still waiting for goofy to open its RPC; print a friendly
            # error message
            status_summary = (
                'Waiting patiently for goofy to accept RPC connections...')

        if status_summary != last_status_summary:
          logging.info(status_summary)
          last_status_summary = status_summary
        if time.time() - start >= self.TIMEOUT_SECS:
          sys.exit('goofy did not come up after %s seconds' % self.TIMEOUT_SECS)
        time.sleep(self.POLL_INTERVAL_SECS)


class DeviceDataCommand(Subcommand):
  name = 'device-data'
  help = 'Show the contents of the device data dictionary'

  def Run(self):
    sys.stdout.write(
        yaml.safe_dump(shopfloor.GetDeviceData(),
                       default_flow_style=False))


def main():
  factory.init_logging()
  parser = argparse.ArgumentParser(
      description=(
          'Miscellaneous factory commands for use on DUTs (devices under '
          'test). Use "factory help COMMAND" for more info on a '
          'subcommand.'))
  subparsers = parser.add_subparsers(title='subcommands')

  for _, v in sorted(globals().items()):
    if v != Subcommand and inspect.isclass(v) and issubclass(v, Subcommand):
      subcommand = v()
      assert subcommand.name
      assert subcommand.help
      v.parser = parser
      v.subparsers = subparsers
      v.subparser = subparsers.add_parser(subcommand.name, help=subcommand.help)
      v.subparser.set_defaults(subcommand=subcommand)
      subcommand.Init()

  args = parser.parse_args()
  args.subcommand.args = args
  args.subcommand.Run()


if __name__ == '__main__':
  main()
