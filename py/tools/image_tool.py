#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to manipulate Chrome OS disk & firmware images for manufacturing.

Run "image_tool help" for more info and a list of subcommands.

To add a subcommand, just add a new SubCommand subclass to this file.
"""


from __future__ import print_function

import argparse
import inspect
import logging
import os
import sys


# TODO(hungte) Generalize this (copied from py/tools/factory.py) for all
# commands to utilize easily.
class SubCommand(object):
  """A subcommand.

  Properties:
    name: The name of the command (set by the subclass).
    parser: The ArgumentParser object.
    subparser: The subparser object created with parser.add_subparsers.
    subparsers: A collection of all subparsers.
    args: The parsed arguments.
  """
  name = None  # Overridden by subclass
  aliases = [] # Overridden by subclass

  parser = None
  args = None
  subparser = None
  subparsers = None

  def __init__(self, parser, subparsers):
    assert self.name
    self.parser = parser
    self.subparsers = subparsers
    subparser = subparsers.add_parser(
        self.name, help=self.__doc__.splitlines()[0],
        description=self.__doc__)
    subparser.set_defaults(subcommand=self)
    self.subparser = subparser

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
    raise NotImplementedError


class HelpCommand(SubCommand):
  """Get help on COMMAND"""
  name = 'help'

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


def main():
  parser = argparse.ArgumentParser(
      prog='image_tool',
      description=(
          'Tools to manipulate Chromium OS disk images for factory. '
          'Use "image_tool help COMMAND" for more info on a '
          'subcommand.'))
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='Verbose output')
  subparsers = parser.add_subparsers(title='subcommands')
  argv0 = os.path.splitext(os.path.basename(sys.argv[0]))[0]

  selected_command = None
  for unused_key, v in sorted(globals().items()):
    if v != SubCommand and inspect.isclass(v) and issubclass(v, SubCommand):
      subcommand = v(parser, subparsers)
      subcommand.Init()
      if argv0 in subcommand.aliases:
        selected_command = subcommand.name

  if selected_command:
    args = parser.parse_args([selected_command] + sys.argv[1:])
  else:
    args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - args.verbose * 10)

  args.subcommand.args = args
  args.subcommand.Run()


if __name__ == '__main__':
  main()
