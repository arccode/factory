#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Commandline wrapper for converting csv to yaml parameters."""

import argparse

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf.tools import csv_reader


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--input', action='store', type=str, required=True,
                      help='the path of the root csv file.')
  parser.add_argument('--output', action='store', type=str, required=True,
                      help='the path of output file.')
  args = parser.parse_args()
  python_obj = csv_reader.ReadCsv(args.input)
  with open(args.output, 'w') as fd:
    fd.write(yaml.dump(python_obj, default_flow_style=False))
