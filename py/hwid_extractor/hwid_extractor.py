#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A tool to quickly extract HWID and serial no. from DUT."""

import argparse
import logging
import sys


def ParseArguments(raw_args):
  """Parse command line arguments"""
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', action='count', default=0,
                      help='Logging verbosity.')
  args = parser.parse_args(raw_args)
  return args


def Main(raw_args):
  """main function"""
  args = ParseArguments(raw_args)
  logging.basicConfig(level=logging.WARNING - args.verbosity * 10)
  # TODO(chungsheng@): Add implementation
  raise NotImplementedError('TODO')


if __name__ == '__main__':
  sys.exit(Main(sys.argv[1:]))
