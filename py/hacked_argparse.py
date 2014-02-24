#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hacked argparse module."""

import inspect
import logging
import re
import sys

from argparse import ArgumentParser, Action

import factory_common   # pylint: disable=W0611
from cros.factory.common import CheckDictKeys


class HackedArgParser(ArgumentParser):
  """Replace the usage and help strings to better format command names.

  The default formatting is terrible, cramming all the command names
  into one line with no spacing so that they are very hard to
  copy-paste.  Instead format command names one-per-line.  For
  simplicity make usage just return the help message text.

  Reformatting is done using regexp-substitution because the argparse
  formatting internals are explicitly declared to be private, and so
  doing things this way should be no less fragile than trying to
  replace the relevant argparse internals.
  """

  def __init__(self, subcommands=None, **kvargs):
    self.subcommands = subcommands if subcommands is not None else {}
    ArgumentParser.__init__(self, **kvargs)

  def format_sub_cmd_menu(self):
    """Return str with aligned list of 'cmd-name : first-doc-line' strs."""
    max_cmd_len = (max(len(c) for c in self.subcommands) if self.subcommands
                   else 0)
    def format_item(cmd_name):
      doc = self.subcommands[cmd_name][1]
      if doc is None:
        doc = ''
      else:
        doc = (': ' + (max_cmd_len - len(cmd_name)) * ' ' +
               doc.split('\n')[0])
      return '  ' + cmd_name + doc
    return '\n'.join(
        format_item(cmd_name) for cmd_name in sorted(self.subcommands))

  def format_help(self):
    s = ArgumentParser.format_help(self)
    if self.subcommands:
      s = re.sub(r'(?ms)\].*{.*}.*\.\.\.', r'] <sub-command>', s)
      s = re.sub(r'(?ms)(positional.*)(optional arguments:)',
                 r'sub-commands:\n%s\n\n\2' % self.format_sub_cmd_menu(), s)
    return s

  def format_usage(self):
    return self.format_help() + '\n'


def CmdArg(*args, **kwargs):
  """Allow decorator arg specification using real argparse syntax."""
  return (args, kwargs)


class VerbosityAction(Action):
  """A function to set logging verbosity."""
  def __call__(self, parser, namespace, values, option_string=None):
    logging_level = {4: logging.DEBUG, 3: logging.INFO, 2: logging.WARNING,
                     1: logging.ERROR, 0: logging.CRITICAL}[int(values)]
    setattr(namespace, self.dest, logging_level)


verbosity_cmd_arg = CmdArg(
    '-v', '--verbosity', choices='01234', default=logging.WARNING,
    action=VerbosityAction)


# Map the caller frame to subcommands
_caller_subcommands_map = {}

def Command(cmd_name, *args):
  """Decorator to populate the per-module sub-command list.

  If not already present, a SUB_CMD_LIST_ATTR attribute is created in
  the caller module.  This attribute is then populated with the list
  of subcommands.

  Function doc strings are extracted and shown to users as part of the
  help message for each command.
  """
  caller = inspect.getouterframes(inspect.currentframe())[1][1]
  def Decorate(fun):
    doc = fun.__doc__ if fun.__doc__ else None
    subcommands = (_caller_subcommands_map[caller] if caller in
                   _caller_subcommands_map else {})
    subcommands[cmd_name] = (fun, doc, args)
    _caller_subcommands_map[caller] = subcommands
    return fun
  return Decorate


def ParseCmdline(top_level_description, *common_args, **kwargs):
  """Return object containing all argparse-processed command line data.

  The list of subcommands is taken from the SUB_CMD_LIST_ATTR
  attribute of the caller module.
  """
  # pylint: disable=C9011
  CheckDictKeys(kwargs, ['args_to_parse'])

  common_parser = HackedArgParser(add_help=False)
  for (tags, kvargs) in common_args:
    common_parser.add_argument(*tags, **kvargs)

  caller = inspect.getouterframes(inspect.currentframe())[1][1]
  subcommands = (_caller_subcommands_map[caller] if caller in
                 _caller_subcommands_map else {})
  parser = HackedArgParser(
      subcommands=subcommands,
      description=top_level_description,
      parents=[common_parser])
  subparsers = parser.add_subparsers(dest='command_name')
  for cmd_name, (fun, doc, arg_list) in subcommands.items():
    subparser = subparsers.add_parser(cmd_name, description=doc,
                                      parents=[common_parser],
                                      conflict_handler='resolve')
    subparser.set_defaults(command_name=cmd_name, command=fun)
    for (tags, kvargs) in arg_list:
      subparser.add_argument(*tags, **kvargs)
  return parser.parse_args(kwargs.get('args_to_parse', sys.argv[1:]))
