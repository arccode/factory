#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import inspect
import logging
import re

from argparse import ArgumentParser, Action


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
      doc = '' if doc is None else ' : ' + doc.split('\n')[0]
      return (max_cmd_len - len(cmd_name) + 2) * ' ' + cmd_name + doc
    return '\n'.join(
        format_item(cmd_name) for cmd_name in sorted(self.subcommands))

  def format_help(self):
    s = ArgumentParser.format_help(self)
    s = re.sub(r'(?ms)\].*{.*}.*\.\.\.', r'] <sub-command>', s)
    s = re.sub(r'(?ms)(positional.*)(optional arguments:)',
               r'sub-commands:\n%s\n\n\2' % self.format_sub_cmd_menu(), s)
    return s

  def format_usage(self):
    return self.format_help() + '\n'


def CmdArg(*tags, **kvargs):
  """Allow decorator arg specification using real argparse syntax."""
  return (tags, kvargs)


class VerbosityAction(Action):
  def __call__(self, parser, namespace, values, option_string=None):
    logging_level = {4: logging.DEBUG, 3: logging.INFO, 2: logging.WARNING,
                     1: logging.ERROR, 0: logging.CRITICAL}[int(values)]
    setattr(namespace, self.dest, logging_level)


verbosity_cmd_arg = CmdArg(
    '-v', '--verbosity', choices='01234', default=logging.WARNING,
    action=VerbosityAction)


# Per-module attribute to contain dict of (sub-command-name : function) pairs.
SUB_CMD_LIST_ATTR = 'G_subcommands'


def Command(cmd_name, *arg_list):
  """Decorator to populate the per-module sub-command list.

  If not already present, a SUB_CMD_LIST_ATTR attribute is created in
  the caller module.  This attribute is then populated with the list
  of subcommands.

  Function doc strings are extracted and shown to users as part of the
  help message for each command.
  """
  caller_module = inspect.getmodule((inspect.stack()[1])[0])
  def Decorate(fun):
    doc = fun.__doc__ if fun.__doc__ else None
    subcommands = getattr(caller_module, SUB_CMD_LIST_ATTR, {})
    subcommands[cmd_name] = (fun, doc, arg_list)
    setattr(caller_module, SUB_CMD_LIST_ATTR, subcommands)
    return fun
  return Decorate


def ParseCmdline(top_level_description, *common_args):
  """Return object containing all argparse-processed command line data.

  The list of subcommands is taken from the SUB_CMD_LIST_ATTR
  attribute of the caller module.
  """
  caller_module = inspect.getmodule((inspect.stack()[1])[0])
  subcommands = getattr(caller_module, SUB_CMD_LIST_ATTR, {})
  parser = HackedArgParser(
      subcommands=subcommands,
      description=top_level_description)
  for (tags, kvargs) in common_args:
    parser.add_argument(*tags, **kvargs)
  subparsers = parser.add_subparsers(dest='command_name')
  for cmd_name, (fun, doc, arg_list) in subcommands.items():
    subparser = subparsers.add_parser(cmd_name, description=doc)
    subparser.set_defaults(command_name=cmd_name, command=fun)
    for (tags, kvargs) in arg_list:
      subparser.add_argument(*tags, **kvargs)
  return parser.parse_args()
