#!/usr/bin/env python2
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Creates a tiny self-contained Python executable.

This is similar to "make_par", in a more general and lightweight way.
The generated executable contains only the modules you have explicitly
specified, and can be used to execute them as main. Note you have to include
all dependent modules explicitly - this script won't try to load modules to
solve dependency.

After the PAR file is created, run it with a symlink to the expected command
name or specify the command as first argument to execute.

For examples:

  # Run the program with native name.
  tiny_par -o pygpt -m cros.factory.utils.pygpt
  ./pygpt ...

  # Select using symlinks.
  tiny_par -o tools.par \
      -m cros.factory.utils.pygpt \
      -m cros.factory.tools.image_tool
  ln -s tools.par pygpt
  ln -s tools.par image_tool
  ./pygpt ...
  # Select using explicitly command name.
  ./tools.par pygpt ...
"""

from __future__ import print_function

import argparse
import glob
import logging
import os
import shutil
import tempfile
import zipfile


# A pattern in TEMPLATE to be replaced with real module list.
MODULES_PATTERN = '__MODULES_HERE__'

# The template is a stub to be inserted in the beginning of output PAR file.
TEMPLATE = """#!/bin/sh
EXEC_FILE="$(basename "$0")"
REAL_PATH="$(readlink -f "$0")"
REAL_DIR="$(dirname "${REAL_PATH}")"
COMMANDS=""
MODULES="__MODULES_HERE__"
MODULE=""

find_command() {
  local command="$1" module="" name=""
  COMMANDS=""
  for module in ${MODULES}; do
    name="${module##*.}"
    if [ "${name}" = "${command}" ]; then
      MODULE="${module}"
      return 0
    fi
    COMMANDS="${COMMANDS} ${name}"
  done
  return 1
}

if ! find_command "${EXEC_FILE}"; then
  if find_command "$1"; then
    shift
  else
    echo "ERROR: No ${EXEC_FILE} in ${REAL_PATH}. Available:${COMMANDS}" >&2
    exit 1
  fi
fi

export PYTHONPATH="${PYTHONPATH}:${REAL_PATH}"
export PAR_PATH="${REAL_PATH}"
export PATH="${PATH}:${REAL_DIR}"
exec python2 -m "${MODULE}" "$@"
exit 1
# Should never reach here. Anything below are reserved for ZIP.
"""


def CollectFiles(pkg_dir, modules, output, init_modules):
  """Collects files needed from modules into given output folder.

  Args:
    pkg_dir: a path to the root of modules.
    modules: a list of string for Python module (a.b.c).
    output: a path to the root of output.
    init_modules: a list of string for __init__ style modules.
  """
  for module in modules:
    src_path = module.replace('.', '/') + '.py'
    par_dir = os.path.dirname(src_path)
    dest_path = output

    # Build directory and init files.
    for entry in par_dir.split('/'):
      dest_path = os.path.join(dest_path, entry)
      if os.path.exists(dest_path):
        continue

      logging.debug('%s => %s (mkdir + init)', src_path, dest_path)
      os.mkdir(dest_path)
      for init in init_modules:
        with open(os.path.join(dest_path, init + '.py'), 'a'):
          pass

    # Copy the real module file.
    logging.debug('%s => %s', src_path, dest_path)
    shutil.copy(os.path.join(pkg_dir, src_path), dest_path)


def BuildPythonZip(py_dir, zip_name='_stage.zip'):
  """Builds a Python zip file from given directory.

  Args:
    py_dir: a path to folder with all Python files available.
    zip_name: the file name to be created.

  Returns:
    A path to the created Zip file (in py_dir).
  """
  targets = glob.glob(os.path.join(py_dir, '*'))
  zip_path = os.path.join(py_dir, zip_name)
  with zipfile.PyZipFile(zip_path, 'w') as par_file:
    for target in targets:
      par_file.writepy(target)
  return zip_path


def main(argv=None):
  parser = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--output', '-o', default='tinypar.par',
      help='output file. default: %(default)s')
  parser.add_argument(
      '--pkg', '-k', default='.',
      help='path to the Python package folder to find modules.')
  parser.add_argument(
      '-m', '--module', dest='modules', action='append', default=[],
      help='include given module with main (which can be a command).')
  parser.add_argument(
      '--extra_init', default='factory_common',
      help=('extra init-like file to create in each module directory. '
            'default: %(default)s'))
  parser.add_argument(
      '--verbose', '-v', action='count', help='increase output verbosity.')
  # TODO(hungte) Add an option to add extra PATH in invocation.
  # TODO(hungte) Add an option to "add dependency but not as executable".
  # TODO(hungte) Add an option to "add a full directory".
  args = parser.parse_args(argv)
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  if not args.modules:
    exit('ERROR: Need at least one module (-m).')

  init_modules = ['__init__']
  if args.extra_init:
    init_modules += [args.extra_init]

  tmp_dir = os.path.realpath(tempfile.mkdtemp(prefix='tiny_par.'))
  try:
    CollectFiles(args.pkg, args.modules, tmp_dir, init_modules)
    zip_path = BuildPythonZip(tmp_dir)
    with open(args.output, 'w') as f:
      f.write(TEMPLATE.replace(MODULES_PATTERN, ' '.join(args.modules)))
      with open(zip_path, 'r') as z:
        f.write(z.read())
    os.chmod(args.output, 0o755)
    print('Successfully created PAR executable: %s' % args.output)
  finally:
    shutil.rmtree(tmp_dir)



if __name__ == '__main__':
  main()
