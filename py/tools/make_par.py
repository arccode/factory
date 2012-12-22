#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Creates a self-extracting Python executable."""

DESCRIPTION = """Creates a self-extracting Python executable.

The generated executable contains a copy of the entire factory code
and can be used to executed any "well-behaved" executable, in
particular the shopfloor server and tools like mount_partition.  Simply
generate an output file whose name is the same as any symlink in the bin
directory, or create a symlink to the generated archive with such a name.

For instance:

  make_par -o shopfloor_server
  # ./shopfloor_server is now a fully-functional, standalone shopfloor server
  # including all dependencies.

or:

  make_par  # Generates factory.par
  ln -s factory.par shopfloor_server
  ln -s factory.par mount_partition
  # You can now run either ./shopfloor_server or ./mount_partition.
"""

import argparse
import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn, SpawnOutput

# Template for the header that will be placed before the ZIP file to
# execute a script based on the name which is used to execute it.  The
# literal string "MODULES" is replaced with a map from executable name
# to fully-qualified module name (e.g., {'mount_partition':
# 'cros.factory.tools.mount_partition'}).
HEADER_TEMPLATE = """#!/bin/sh

exec \
  env PYTHONPATH="$(readlink -f $0):$PYTHONPATH" \
      PYTHONIOENCODING=utf-8 \
  python -c \
"import os, runpy, sys

# Remove '-c' from argument list.
sys.argv = sys.argv[1:]

# List of modules, based on symlinks in 'bin' when make_par was run.
# The actual list is substituted in by the make_par script.
modules = MODULES

# Use the name we were executed as to determine which module to run.
name = os.path.basename(sys.argv[0])
module = modules.get(name)

if not module:
  # Display an error message describing the valid commands.
  print >>sys.stderr, (
    'Unable to run %s.  To run a file within this archive,' % name)
  print >>sys.stderr, (
    'rename it to (or create a symbolic link from) one of the following:')
  print >>sys.stderr
  for m in sorted(modules.keys()):
    print >>sys.stderr, '  %s' % m
  sys.exit(1)

runpy.run_module(module, run_name='__main__')" "$0" "$@"

echo Unable to exec "$*" >& 2
exit 1

# ZIP file follows...
"""

def main(argv=None):
  parser = argparse.ArgumentParser(
    description=DESCRIPTION,
    formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument(
      '--output', '-o', metavar='FILE', default='factory.par',
      help='output file (default: %(default)s')
  args = parser.parse_args(argv)
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  tmp = tempfile.mkdtemp(prefix='make_par.')
  try:
    # Make factory.par file with make.
    Spawn(['make', '-s', '-C', factory.FACTORY_PATH, 'par',
           'PAR_DEST_DIR=%s' % tmp],
          log=True, check_call=True)
    par_file = os.path.join(tmp, 'factory.par')

    # Build a map of runnable modules based on symlinks in bin.
    modules = {}
    factory_bin = os.path.join(factory.FACTORY_PATH, 'bin')
    for f in glob.glob(os.path.join(factory_bin, '*')):
      if not os.path.islink(f):
        continue
      dest = os.readlink(f)
      match = re.match('\.\./py/(.+)\.py$', dest)
      if not match:
        continue

      module = 'cros.factory.%s' % match.group(1).replace('/', '.')
      name = module.rpartition('.')[2]
      logging.info('Mapping binary %s to %s', name, module)
      modules[name] = module

    # Concatenate the header and the par file.
    with open(args.output, 'wb') as out:
      out.write(HEADER_TEMPLATE.replace('MODULES', repr(modules)))
      shutil.copyfileobj(open(par_file), out)
      os.fchmod(out.fileno(), 0755)

    # Done!
    print 'Created %s (%d bytes)' % (args.output, os.path.getsize(args.output))

    # Sanity check: make sure we can run 'make_par --help' within the
    # archive, in a totally clean environment, and see the help
    # message.
    try:
      link = os.path.join(tmp, 'make_par')
      os.symlink(os.path.realpath(args.output), link)
      output = SpawnOutput(
        [link, '--help'], env={}, cwd='/',
        check_call=True, read_stdout=True,log_stderr_on_error=True)
      if 'show this help message and exit' not in output:
        logging.error('Unable to run "make_par --help": output is %r', output)
    except subprocess.CalledProcessError:
      logging.error('Unable to run "make_par --help" within the .par file')
      return False

    return True
  finally:
    shutil.rmtree(tmp)

if __name__ == '__main__':
  sys.exit(0 if main() else 1)
