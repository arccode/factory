#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Creates a self-extracting Python executable."""

from __future__ import print_function

import argparse
from distutils.sysconfig import get_python_lib
import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.process_utils import SpawnOutput

DESCRIPTION = """Creates a self-extracting Python executable.

The generated executable contains a copy of the entire factory code
and can be used to executed any "well-behaved" executable, in
particular the factory server and tools like mount_partition.  Simply
generate an output file whose name is the same as any symlink in the bin
directory, or create a symlink to the generated archive with such a name.

For instance:

  make_par -o factory_server
  # ./factory_server is now a fully-functional, standalone factory server
  # including all dependencies.

or:

  make_par  # Generates factory.par
  ln -s factory.par factory_server
  ln -s factory.par mount_partition
  # You can now run either ./factory_server or ./mount_partition.
"""

# Template for the header that will be placed before the ZIP file to
# execute a script based on the name which is used to execute it.  The
# literal string "MODULES" is replaced with a map from executable name
# to fully-qualified module name (e.g., {'mount_partition':
# 'cros.factory.tools.mount_partition'}).
HEADER_TEMPLATE = """#!/bin/sh

# This par file.
par="$(readlink -f $0)"
# The directory this par file is in.
dir="$(dirname "$par")"

if [ -e $dir/factory_common.py ]; then
  # The .par file has been expanded.  Print a warning and use the expanded
  # file.
  echo WARNING: factory.par has been unzipped. Using the unzipped files. >& 2
  export PYTHONPATH="$dir":"$PYTHONPATH"
else
  export PYTHONPATH="$par":"$PYTHONPATH"
fi

export PYTHONIOENCODING=utf-8

exec python2 -c \
"import os, runpy, sys

# Remove '-c' from argument list.
sys.argv = sys.argv[1:]

# List of modules, based on symlinks in 'bin' when make_par was run.
# The actual list is substituted in by the make_par script.
modules = MODULES

# Use the name we were executed as to determine which module to run.
if sys.argv[0].endswith('.par') and len(sys.argv) > 1:
  # Not run as a symlink; remove argv[0].  This allows you to run, e.g.,
  # factory.par gooftool probe.
  sys.argv = sys.argv[1:]

name = os.path.basename(sys.argv[0])
module = modules.get(name)

# Set the process title, if available
try:
  from setproctitle import setproctitle
  setproctitle(' '.join(sys.argv))
except Exception:
  pass  # Oh well

# Set process title so killall/pkill will work.
try:
  import ctypes
  buff = ctypes.create_string_buffer(len(name) + 1)
  buff.value = name
  ctypes.cdll.LoadLibrary('libc.so.6').prctl(15, ctypes.byref(buff), 0, 0, 0)
except Exception:
  pass  # Oh well

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
  parser.add_argument(
      '--add-zip', action='append', default=[],
      help='zip files containing extra files to include')
  parser.add_argument(
      '--mini', action='store_true',
      help='Build smaller version suitable for installation into test image')
  parser.add_argument(
      '--compiled', action='store_true',
      help='Build with compiled python code (*.pyc).')
  parser.add_argument(
      '--include-unittest', action='store_true',
      help='Build with unittest files for self testing')
  args = parser.parse_args(argv)
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  tmp = os.path.realpath(tempfile.mkdtemp(prefix='make_par.'))
  try:
    par_build = os.path.join(tmp, 'par_build')
    os.mkdir(par_build)

    # Copy our py sources and bins, and any overlays, into the src
    # directory.
    src = os.path.join(tmp, 'src')
    os.mkdir(src)
    Spawn(['rsync', '-a',
           '--exclude', '/py/dome',
           '--exclude', '/py/test_list_editor',
           '--exclude', '/py/umpire/server',
           os.path.join(paths.FACTORY_DIR, 'py'),
           os.path.join(paths.FACTORY_DIR, 'bin'),
           src],
          log=True, check_call=True)
    # Add files from overlay.
    for f in args.add_zip:
      Spawn(['unzip', '-oq', f, '-d', src],
            log=True, check_call=True)

    cros_dir = os.path.join(par_build, 'cros')
    os.mkdir(cros_dir)

    rsync_args = ['rsync', '-a']

    if not args.include_unittest:
      rsync_args += ['--exclude', '*_unittest.py', '--exclude', 'testdata']

    rsync_args += [
        '--exclude', 'factory_common.py*',
        '--exclude', '*.pyo',  # pyo will discard assert.
        '--include' if args.compiled else '--exclude', '*.pyc',
        '--include', '*.py']

    if args.mini:
      # Exclude some piggy directories we'll never need for the mini
      # par, since we will not run these things in a test image.
      rsync_args.extend(['--exclude', 'static',
                         '--exclude', 'goofy',
                         '--exclude', 'pytests'])
    else:
      rsync_args.extend(['--include', '*.css',
                         '--include', '*.csv',
                         '--include', '*.html',
                         '--include', '*.js',
                         '--include', '*.png',
                         '--include', '*.json',
                         # We must include instalog/utils explicitly, as it is
                         # a symlink that would otherwise be excluded
                         # by the * wildcard.
                         '--include', 'instalog/utils',
                         # We must include testlog/utils explicitly, as it is
                         # a symlink that would otherwise be excluded
                         # by the * wildcard.
                         '--include', 'testlog/utils'])

    rsync_args.extend([
        '--include', '*/',
        '--exclude', '*',
        os.path.join(src, 'py/'),
        os.path.join(cros_dir, 'factory')])
    Spawn(rsync_args, log=True, check_call=True)

    # Copy necessary third-party packages. They are already present in test
    # images, so no need in mini version.
    if not args.mini:
      python_lib = get_python_lib()

      rsync_args = ['rsync', '-a',
                    os.path.join(python_lib, 'enum'),
                    os.path.join(python_lib, 'google'),
                    os.path.join(python_lib, 'jsonrpclib'),
                    os.path.join(python_lib, 'yaml')]

      rsync_args.append(par_build)
      Spawn(rsync_args, log=True, check_call=True,
            cwd=paths.FACTORY_DIR)

    # Add empty __init__.py files so Python realizes these directories
    # are modules.
    open(os.path.join(cros_dir, '__init__.py'), 'w')
    open(os.path.join(cros_dir, 'factory', '__init__.py'), 'w')

    # Add an empty factory_common file (since many scripts import
    # factory_common).
    open(os.path.join(par_build, 'factory_common.py'), 'w')

    if args.compiled:
      Spawn(['python2', '-m', 'compileall', par_build], check_call=True)

    # Zip 'em up!
    factory_par = os.path.join(tmp, 'factory.par')

    Spawn(['zip', '-qr', factory_par, '.'],
          check_call=True, log=True, cwd=par_build)

    # Build a map of runnable modules based on symlinks in bin.
    modules = {}
    bin_dir = os.path.join(src, 'bin')
    for f in glob.glob(os.path.join(bin_dir, '*')):
      if not os.path.islink(f):
        continue
      dest = os.readlink(f)
      match = re.match(r'\.\./py/(.+)\.py$', dest)
      if not match:
        continue

      module = 'cros.factory.%s' % match.group(1).replace('/', '.')
      name = module.rpartition('.')[2]
      logging.info('Mapping binary %s to %s', name, module)
      modules[name] = module
      # Also map the name of symlink to binary.
      link_name = os.path.basename(f)
      if link_name != name:
        logging.info('Mapping binary %s to %s', link_name, module)
        modules[link_name] = module

    # Concatenate the header and the par file.
    with open(args.output, 'wb') as out:
      out.write(HEADER_TEMPLATE.replace('MODULES', repr(modules)))
      shutil.copyfileobj(open(factory_par), out)
      os.fchmod(out.fileno(), 0o755)

    # Done!
    print('Created %s (%d bytes)' % (args.output, os.path.getsize(args.output)))

    # Sanity check: make sure we can run 'make_par --help' within the
    # archive, in a totally clean environment, and see the help
    # message.
    try:
      link = os.path.join(tmp, 'make_par')
      os.symlink(os.path.realpath(args.output), link)
      output = SpawnOutput(
          [link, '--help'], env={}, cwd='/',
          check_call=True, read_stdout=True, log_stderr_on_error=True)
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
