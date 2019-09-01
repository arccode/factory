#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An utility to convert existing YAML files to JSON format."""


from __future__ import print_function

import json
import os
import sys

import yaml


def ConvertYAMLToJSON(yaml_str, pretty_print=True):
  kargs = dict(
      indent=1, separators=(',', ': '), sort_keys=True) if pretty_print else {}
  return json.dumps(yaml.load(yaml_str), **kargs)


def ConvertYAMLPathToJSONPath(yaml_path):
  """Try to strip '.yaml' file extension and return a name ends with '.json'."""
  name, ext = os.path.splitext(yaml_path)
  if ext.lower() != '.yaml':
    name = yaml_path
  return name + '.json'


def main():
  if not 1 < len(sys.argv) < 4:
    exit('Usage: %s input [output]' % sys.argv[0])
  in_file = sys.argv[1]
  out_file = sys.argv[2] if len(sys.argv) > 2 else (
      ConvertYAMLPathToJSONPath(in_file))
  print('%s => %s' % (in_file, out_file))
  with open(in_file) as f_in:
    with open(out_file, 'w') as f_out:
      f_out.write(ConvertYAMLToJSON(f_in.read()))


if __name__ == '__main__':
  main()
