#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Execute an unittest in factory.par

To check the behavior of factory.par, we want to run execute some unittest
within PAR.
"""

import argparse
import importlib
import logging
import unittest


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('unittest_path',
                      help=('Python module path to load unittest test cases, '
                            'e.g. "cros.factory.utils.config_utils_unittest"'))

  args = parser.parse_args()

  # Since this script is probably called by another unittest, the output might
  # be dropped and cause confusion if we are using logging.info.
  logging.warning('run_unittest_in_par: module=%s', args.unittest_path)

  module = importlib.import_module(args.unittest_path)
  suite = unittest.TestLoader().loadTestsFromModule(module)
  unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == '__main__':
  if '.par' not in __file__.lower():
    raise Exception(
        'It makes no sense to run this script directly, sample usage: '
        'factory.par run_unittest_in_par <unittest_module>')
  main()
