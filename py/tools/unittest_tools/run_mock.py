#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import ast

import mock_loader


def RunPytest(pytest, args):
  """Parse the args, create a pytest instance, and run the test."""
  # We should import utils.arg_utils and test.utils.pytest_utils
  # after importing mock_loader since these two files might import
  # other files under cros.factory
  from cros.factory.utils.arg_utils import Args
  from cros.factory.test.utils import pytest_utils
  test = pytest_utils.LoadPytest(pytest)()
  arg_spec = test.ARGS or []
  test.args = Args(*arg_spec).Parse(args or {})
  test.setUp()
  test.runTest()
  test.tearDown()


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      'pytest', metavar='TEST_NAME',
      help='Name of the pytest within the current directory, e.g., '
      '"thermal_slope"')
  parser.add_argument(
      '--args', help='''Dictionary of arguments, e.g., "{'foo': 'bar'}"''')
  parser.add_argument('--verbose', '-v', action='store_true')
  cli_args = parser.parse_args()
  args = (
      ast.literal_eval(cli_args.args) if cli_args.args else {})

  with mock_loader.Loader():
    # Run Pytest without goofy
    RunPytest(cli_args.pytest, args)


if __name__ == "__main__":
  main()
