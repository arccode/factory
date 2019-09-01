#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to create 'resource' files for Chromium OS factory build system.

This utility scans for *.rsrc, and creates the resource files based on the rules
defined in rsrc files.

See the URL for more details:
https://chromium.googlesource.com/chromiumos/platform/factory/+/master/resources/README.md
"""


from __future__ import print_function

import argparse
import glob
import itertools
import logging
import os
import tarfile


RSRC_FILES = '*.rsrc'


class ResourceError(Exception):
  """All exceptions when creating resources."""
  pass


def AddResource(output, rule, args):
  """Adds one resource from given rule to output (tar) object.

  output: A tarfile.TarFile instance for adding resource into.
  rule: A string in SRC[:DEST] format.
  args: the environment arguments for sysroot, board files, and resources.
  """
  is_optional = rule.startswith('?')
  if is_optional:
    rule = rule[1:]

  src, dest = rule.split(':') if ':' in rule else (rule, rule)
  logging.info('%s => %s%s', src, dest, ' (optional)' if is_optional else '')
  if os.path.isabs(src):
    src_list = [os.path.join(args.sysroot, '.' + src)]
  else:
    src_list = [os.path.normpath(os.path.join(args.resources, src))]
    if args.board_resources:
      src_list += [os.path.normpath(os.path.join(args.board_resources, src))]

  found = 0
  for src_path in src_list:
    if not os.path.exists(src_path):
      continue
    found += 1
    logging.debug('Add: %s=>%s', src_path, dest)
    output.add(src_path, dest)

  if found < 1:
    if is_optional:
      logging.info('skip non-exist optional resource: %s', src)
      return
    raise ResourceError('Failed to find input resource: %s' % src)


def CreateResource(resource, input_list, args):
  """Creates a resource file by descriptions in input_list.

  resource: the name of the resource file to create.
  input_list: a list of RSRC files for creating the resource file.
  args: the environment arguments for sysroot, board files, and resources.
  """
  logging.info('Creating resource [%s]...', resource)
  with tarfile.open(os.path.join(args.output_dir, resource + '.tar'), 'w',
                    dereference=True) as t:
    for input_file in input_list:
      with open(input_file) as f:
        for rule in f.readlines():
          rule = rule.strip()
          if rule.startswith('#') or not rule:
            continue
          AddResource(t, rule, args)


def CreateAllResources(args):
  """Scans and creates all resources from *.rsrc files."""

  def GetResourceName(rc_path):
    """Returns the derived resource name from an rsrc file.

    The rsrc file name should be in format <resource-name>.[<sub-name>*.]rsrc

    resource-name will be used to construct the name of output file.
    sub-name will be simply discarded - this is to help packing multiple files
    from multiple import files (i.e., sharing definition files between multiple
    output files).
    """
    return os.path.basename(rc_path).partition('.')[0]

  rc_files = glob.glob(os.path.join(args.resources, RSRC_FILES))
  if args.board_resources:
    rc_files += glob.glob(os.path.join(args.board_resources, RSRC_FILES))
  rc_files.sort()
  rc_groups = {name: list(paths) for name, paths in itertools.groupby(
      rc_files, GetResourceName)}
  logging.debug('rc_groups: %r', rc_groups)
  for resource, input_list in rc_groups.iteritems():
    CreateResource(resource, input_list, args)


def main():
  parser = argparse.ArgumentParser(
      description=(__doc__))
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='Verbose output')
  parser.add_argument('--sysroot', default='/',
                      help='directory to search for absolute path resource')
  parser.add_argument('--resources', default='.',
                      help='path to "resources/" to search for relative files')
  parser.add_argument('--board_resources',
                      help='BOARD_FILES_DIR/resources for relative resource')
  parser.add_argument('--output_dir', default='.',
                      help='directory to put generated resources')
  args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - args.verbose * 10)

  try:
    CreateAllResources(args)
  except Exception as e:
    print('ERROR: %s' % e)
    exit(1)


if __name__ == '__main__':
  main()
