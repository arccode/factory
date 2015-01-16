#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Standalone test driver.

Note that this is tested indirectly by make_par_unittest.py.
'''

from __future__ import print_function

import argparse
import logging
import os
import pickle
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import invocation
from cros.factory.test import factory
from cros.factory.utils import file_utils


def RunPyTest(name, args):
  '''Runs a pytest.

  Args:
    name: The name of the test within the pytests module (e.g.,
      "thermal_slope").
    args: The argument dictionary.

  Returns:
    True if the test passed.
  '''
  with file_utils.UnopenedTemporaryFile(prefix='results') as results:
    info = invocation.PyTestInfo(None, None, name, args, results)
    invocation.RunPytest(info)
    return pickle.load(open(results))[0] == factory.TestState.PASSED


def main():
  # Unbuffer stdout
  sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

  parser = argparse.ArgumentParser()
  # TODO(jsalz): Read the test's ARGS and use argparse to parse
  # test-specific arguments and print test-specific help.
  parser.add_argument(
      '--args',
      help='''Dictionary of arguments, e.g., "{'foo': 'bar'}"''')
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument(
      'pytest', metavar='TEST_NAME',
      help='Name of the pytest within the pytests module, e.g., '
           '"thermal_slope"')
  args = parser.parse_args()
  logging.basicConfig(level=(logging.INFO - 10 * (args.verbose or 0)))

  passed = RunPyTest(args.pytest, eval(args.args) if args.args else {})
  sys.exit(0 if passed else 1)


if __name__ == '__main__':
  main()
