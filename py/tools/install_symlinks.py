#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Installs symlinks to factory binaries, based on symlinks.yaml.

See misc/symlinks.yaml for more information on installation modes, and
a list of symlinks that are installed.
"""

import argparse
import logging
import os
import sys

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.schema import Dict
from cros.factory.utils.schema import FixedDict
from cros.factory.utils.schema import Scalar


# Schema for symlinks.yaml.
SYMLINKS_SCHEMA = FixedDict(
    'binaries',
    items={'binaries': Dict('binaries',
                            Scalar('bin', str),
                            Scalar('mode', str, ['full', 'mini']))})

# Valid modes.
MODE_FULL = 'full'  # Install all binaries
MODE_MINI = 'mini'  # Install only factory-mini binaries


def InstallSymlinks(target, dest, mode, sudo=False, symlinks=None):
  """Installs symlinks to factory binaries.

  Args:
    target: Path to the directory actually containing the binaries,
        or a .par file to which binaries will be linked.
    dest: The directory in which the symlinks will be created.
    mode: The mode for installation: 'mini' to install only binaries
        for factory-mini.par, or 'full' to install all binaries.
    sudo: Whether to sudo when creating the links.
    symlinks: The parsed contents of the symlinks.yaml file.  If
        None, this is loaded from symlinks.yaml.

  Returns:
    A list of names of symlinks binaries.
  """
  assert mode in [MODE_MINI, MODE_FULL]

  if not symlinks:
    with open(os.path.join(paths.FACTORY_DIR,
                           'misc/symlinks.yaml')) as f:
      symlinks = yaml.load(f)

  SYMLINKS_SCHEMA.Validate(symlinks)

  # Binaries that we have linked.
  linked = []

  Spawn(['mkdir', '-p', dest], check_call=True, log=True, sudo=sudo)

  for item_name, item_mode in sorted(symlinks['binaries'].items()):
    link_path = os.path.join(dest, item_name)
    if item_mode == 'full' and mode == 'mini':
      # The item works only with the full toolkit, but we are
      # installing symlinks for factory-mini.par.  Don't write the
      # symlink.
      logging.info('Skipping %s', item_name)
      continue

    linked.append(item_name)
    if target.endswith('.par'):
      target_path = target
    else:
      target_path = os.path.join(target, os.path.basename(link_path))
    Spawn(['ln', '-sf', target_path, link_path], log=True, check_call=True,
          sudo=sudo)

  return linked


def main(argv=None, out=sys.stdout):
  parser = argparse.ArgumentParser(
      description='Installs symlinks to factory binaries.')
  parser.add_argument(
      '--mode', choices=['mini', 'full'], metavar='MODE', default='full',
      help=('Whether to install symlinks for the full toolkit or just for '
            'the mini toolkit (default: %(default)s)'))
  parser.add_argument(
      '--target', metavar='TARGETPATH', default='/usr/local/bin',
      help=('Base path for symlink targets; may be a directory or .par file. '
            'The path may be absolute, or relative to DESTPATH '
            '(default: %(default)s)'))
  parser.add_argument(
      '--verbose', '-v', action='store_true', help='Enable verbose logging')
  parser.add_argument(
      'dest', metavar='PATH', nargs=1,
      help='Destination directory for symlinks')
  args = parser.parse_args(sys.argv[1:] if argv is None else argv)
  logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

  linked = InstallSymlinks(args.target, args.dest[0], args.mode)
  out.write('Created symlinks: %s\n' % ' '.join(linked))


if __name__ == '__main__':
  main()
