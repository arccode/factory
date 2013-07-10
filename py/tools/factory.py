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
import sys
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.test import shopfloor
from cros.factory.test.test_lists import test_lists


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


class TestListsCommand(Subcommand):
  name = 'test-lists'
  help = 'Show information about all test lists'

  def Run(self):
    all_test_lists = test_lists.BuildAllTestLists()
    active_id = test_lists.GetActiveTestListId()

    line_format = '%-8s %-20s %s'
    print line_format % ('ACTIVE?', 'ID', 'PATH')

    for k, v in sorted(all_test_lists.items()):
      is_active = '(active)' if k == active_id else ''
      path = (v.path if isinstance(v, test_lists.OldStyleTestList)
              else v.source_path)
      print line_format % (is_active, k, path)


class SetActiveTestListCommand(Subcommand):
  name = 'set-active-test-list'
  help = 'Set the active test list'

  def InitParser(self, subparser):
    subparser.add_argument(
        'id', metavar='ID',
        help=('ID of test list to activate (run '
              '"factory test-lists" to see all available IDs)'))

  def Run(self):
    all_test_lists = test_lists.BuildAllTestLists()

    if self.args.id not in all_test_lists:
      sys.exit('Unknown test list ID %r (use "factory test-lists" to see '
               'available test lists' % self.args.id)
    test_lists.SetActiveTestList(self.args.id)
    print 'Set active test list to %s (wrote %r to %s)' % (
        self.args.id, self.args.id, test_lists.ACTIVE_PATH)


class DeviceDataCommand(Subcommand):
  name = 'device-data'
  help = 'Show the contents of the device data dictionary'

  def Run(self):
    sys.stdout.write(
        yaml.safe_dump(shopfloor.GetDeviceData(),
                       default_flow_style=False))


def main():
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
