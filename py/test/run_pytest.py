#!/usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Standalone test driver.

Note that this is tested indirectly by make_par_unittest.py.
"""

from __future__ import print_function

import argparse
import ast
import inspect
import logging
import os
import pickle
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Args
from cros.factory.test.dut import utils
from cros.factory.test.utils.pytest_utils import LoadPytestModule


def _GetTestCase(pytest):
  """Returns the first test case class found in a given pytest."""
  module = LoadPytestModule(pytest)
  _, test_case = inspect.getmembers(module, lambda obj: (
      inspect.isclass(obj) and issubclass(obj, unittest.TestCase)))[0]
  return test_case


def _FormatErrorMessage(trace):
  """Formats a trace so that the actual error message is in the last
  line.
  """
  # The actual error is in the last line.
  trace, _, error_msg = trace.strip().rpartition('\n')
  error_msg = error_msg.replace('FactoryTestFailure: ', '')
  return error_msg + '\n' + trace


def RunPytest(pytest, args, dut_options, use_goofy=False):
  fn = _RunPytestGoofy if use_goofy else _RunPytestRaw
  return fn(pytest, args, dut_options)


def _RunPytestGoofy(pytest, args, dut_options):
  """Runs a pytest.

  Args:
    pytest: The name of the test within the pytests module (e.g.,
      "thermal_slope").
    args: The argument dictionary.

  Returns:
    A tuple (success, error_message), where:
      - success is a boolean representing the test success/failure
      - error_message is None on success and an error message string on failure
  """
  # Unless this function is called, we would like to avoid these extra
  # dependencies.
  from cros.factory.utils import file_utils
  from cros.factory.goofy import invocation
  from cros.factory.test import factory

  with file_utils.UnopenedTemporaryFile(prefix='results') as results:
    info = invocation.PytestInfo(None, None, pytest, args, results,
                                 dut_options=dut_options)
    invocation.RunPytest(info)
    status, error_msg = pickle.load(open(results))
    return (status == factory.TestState.PASSED, error_msg)


def _RunPytestRaw(pytest, args, dut_options):
  """Runs a pytest with minimal goofy dependencies.

  Args:
    pytest: The name of the test within the pytests module, or the
      unittest.TestCase object to run.
    args: The unverified argument dictionary.
    dut_options: Any dut_options to be passed to the test.

  Returns:
    A tuple (status, error_msg), where:
      - status is a boolean representing the test success/failure
      - error_msg is None on success and an error message string on failure
  """
  # Create a test case instance.
  if isinstance(pytest, str):
    test = _GetTestCase(pytest)()
  else:
    test = pytest()

  # Setup DUT_OPTIONS environment.
  if dut_options:
    os.environ.update({utils.ENV_DUT_OPTIONS: str(dut_options)})

  # Set self.args of the test case.
  try:
    arg_spec = getattr(test, 'ARGS', None)
    setattr(test, 'args', Args(*arg_spec).Parse(args if args else {}))
  except Exception as e:
    return (False, e.message)

  # Run the test.
  result = unittest.TestResult()
  test.run(result)

  # Collect errors and return them.
  all_failures = result.failures + result.errors
  error_msg = None
  if all_failures:
    error_msg = '\n'.join(_FormatErrorMessage(trace)
                          for test_name, trace in all_failures)
  return (error_msg == None, error_msg)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      'pytest', metavar='TEST_NAME',
      help='Name of the pytest within the current directory, e.g., '
           '"thermal_slope"')
  parser.add_argument(
      '--args',
      help='''Dictionary of arguments, e.g., "{'foo': 'bar'}"''')
  parser.add_argument(
      '--dut-options',
      help='''DUT options, e.g., "{'link_class': 'ADBLink'}"''')
  parser.add_argument(
      '--verbose', '-v',
      action='store_true')
  parser.add_argument(
      '--no-use-goofy',
      dest='use_goofy',
      help='Run test with minimal goofy dependencies',
      action='store_false')
  cli_args = parser.parse_args()

  # Set logging level.
  logging_level = logging.DEBUG if cli_args.verbose else logging.INFO
  logging.basicConfig(level=logging_level)

  # Run the test.
  # pylint: disable=W0123
  args = (ast.literal_eval(cli_args.args)
          if cli_args.args else {})
  dut_options = (ast.literal_eval(cli_args.dut_options)
                 if cli_args.dut_options else {})
  # pylint: enable=W0123
  _, error_msg = RunPytest(pytest=cli_args.pytest,
                           args=args,
                           dut_options=dut_options,
                           use_goofy=cli_args.use_goofy)
  # Exit code and error message.
  sys.exit(error_msg or None)


if __name__ == '__main__':
  main()
