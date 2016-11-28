#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command-line interface for probe utilities."""

from __future__ import print_function

import argparse
import json
import logging
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils
from cros.factory.probe import function
from cros.factory.probe.functions import match


_sub_cmd_list = []


def RegisterCommand(cls):
  """Registers the SubCommand class.

  It is the decorator for SubCommand class. The registered class will be added
  to the argument parser.
  """
  _sub_cmd_list.append(cls)
  return cls


class SubCommand(object):
  """The sub-command class."""

  # The sub-command string. Derived class should override it.
  CMD_NAME = ''

  @classmethod
  def AddArgumentToParser(cls, subparsers):
    """Adds the argument parser of the sub-command to the subparsers.

    Args:
      subparsers: the sub-parsers of the root argument parser.
    """
    # Set the docstring of the class as the description.
    subparser = subparsers.add_parser(
        cls.CMD_NAME,
        description=cls.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparser.set_defaults(command=cls.EvalCommand)
    cls._AddArgument(subparser)

  @classmethod
  def _AddArgument(cls, parser):
    """Adds the argument parser of the sub-command to the parser.

    Args:
      parser: a argparse.ArgumentParser object.
    """
    raise NotImplementedError

  @classmethod
  def EvalCommand(cls, options):
    """The method is the main function of the sub-command.

    This method will be evaluated if the sub-command is chosen.

    Args:
      options: the options returned from the argument parser.
    """
    raise NotImplementedError


@RegisterCommand
class EvalFunctionCmd(SubCommand):
  """Evaluates a probe function."""
  CMD_NAME = 'eval-function'

  @classmethod
  def _AddArgument(cls, parser):
    function.LoadFunctions()
    func_list = [func_name for func_name in function.GetRegisteredFunctions()
                 if issubclass(function.GetFunctionClass(func_name),
                               function.ProbeFunction)]
    func_parsers = parser.add_subparsers()
    for func_name in func_list:
      func_cls = function.GetFunctionClass(func_name)
      func_parser = func_parsers.add_parser(
          func_name, description=func_cls.__doc__,
          formatter_class=argparse.RawDescriptionHelpFormatter)
      func_parser.set_defaults(func_cls=func_cls)
      for arg in func_cls.ARGS:
        arg.AddToParser(func_parser)

  @classmethod
  def EvalCommand(cls, options):
    required_args = [arg.name for arg in options.func_cls.ARGS]
    func_args = {key: val for key, val in vars(options).items()
                 if key in required_args}
    results = options.func_cls(**func_args)()
    OutputResults(results, options)


@RegisterCommand
class ProbeCmd(SubCommand):
  """Probe the result according to the configuration file.

  The format of the config file:
  {
    <Component category> : {
      <Component name> : {
        "eval" : <Function expression>,
        "expect" : <Rule expression>
      }
    }
  }

  The format of the results:
  {
    <Component category> : {
      <Component name> : [ <Matched result>, ...  ]
    }
  }
  """
  CMD_NAME = 'probe'

  @classmethod
  def _AddArgument(cls, parser):
    parser.add_argument('config_file',
                        help='The path of probe statement list.')

  @classmethod
  def EvalCommand(cls, options):
    with open(options.config_file, 'r') as f:
      statement_dict = type_utils.UnicodeToString(json.load(f))
    results = {}
    for comp_cls in statement_dict:
      results[comp_cls] = {}
      for comp_name, statement in statement_dict[comp_cls].iteritems():
        logging.info('Probe %s: %s', comp_cls, comp_name)
        results[comp_cls][comp_name] = ProbeStatement(
            statement['eval'], statement['expect'])
    OutputResults(results, options)


def ProbeStatement(func_expression, rule_expression):
  """Evaluates the function expression and filters it by the rule expression."""
  probe_func = function.InterpretFunction(func_expression)
  match_func = match.MatchFunction(rule=rule_expression)
  return match_func(probe_func())


def OutputResults(results, options):
  """Output the results of the sub-command."""
  json_output = json.dumps(results, indent=2)
  if options.output_json_file == '-':  # Output to stdout.
    print(json_output)
  else:
    with open(options.output_json_file, 'w') as f:
      f.write(json_output)


def ParseOptions():
  """Creates the argument parser and returns the parsed options."""
  # Create the root argument parser.
  arg_parser = argparse.ArgumentParser(
      description=sys.modules[__name__].__doc__)
  arg_parser.add_argument('-v', '--verbose', default=False, action='store_true',
                          help='Enable verbose output.')
  arg_parser.add_argument('--output-json-file', default='-',
                          help='Write the JSON output to a file.')

  # Add the argument parser of registered sub-commands.
  subparsers = arg_parser.add_subparsers()
  for sub_cmd in _sub_cmd_list:
    sub_cmd.AddArgumentToParser(subparsers)

  # Parse the argument.
  return arg_parser.parse_args()


def SetRootLogger(verbose):
  # If logging methods are called before basicConfig is called, a default
  # handler will be added into the root logger and ignore basicConfig.
  # Remove it if exists.
  root = logging.getLogger()
  if root.handlers:
    for handler in root.handlers:
      root.removeHandler(handler)

  # Send logging to stderr to keep stdout only containing the results.
  level = logging.DEBUG if verbose else logging.INFO
  logging.basicConfig(level=level, stream=sys.stderr)

def Main():
  options = ParseOptions()
  SetRootLogger(options.verbose)
  options.command(options)


if __name__ == '__main__':
  Main()
