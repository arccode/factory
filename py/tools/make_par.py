#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Creates a self-extracting Python executable.'''

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn

HEADER = """#!/bin/sh

exec \
  env PYTHONPATH="$(readlink -f $0):$PYTHONPATH" \
      PYTHONIOENCODING=utf-8 \
  python -c \
    "import runpy; runpy.run_module('%(module)s', run_name='__main__')" "$@"
echo Unable to exec "$*" >& 2
exit 1

# ZIP file follows...
"""

def main(argv=None):
  parser = argparse.ArgumentParser()
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument(
      '--output', '-o', metavar='FILE',
      help='output file (defaults to <MODULE>.par)')
  parser.add_argument(
      'module', metavar='MODULE',
      help='name of module to be run when the .par file is executed.')
  args = parser.parse_args(argv)
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  if not args.output:
    args.output = args.module.rpartition('.')[2] + '.par'

  tmp = tempfile.mkdtemp(prefix='make_par.')
  try:
    # Make factory.par file with make.
    Spawn(['make', '-s', '-C', factory.FACTORY_PATH, 'par',
           'PAR_DEST_DIR=%s' % tmp],
          log=True, check_call=True)
    par_file = os.path.join(tmp, 'factory.par')

    # Concatenate the header and the par file.
    with open(args.output, 'wb') as out:
      out.write(HEADER % dict(module=args.module))
      shutil.copyfileobj(open(par_file), out)
      os.fchmod(out.fileno(), 0755)

    # Done!
    print 'Created %s (%d bytes)' % (args.output, os.path.getsize(args.output))

    # Sanity check: make sure we can import the module
    try:
      Spawn(['python', '-c', 'import %s' % args.module],
            env={'PYTHONPATH': args.output},
            check_call=True, log_stderr_on_error=True)
    except subprocess.CalledProcessError:
      logging.error('Unable to import %s from %s', args.module, args.output)
      return False

    return True
  finally:
    shutil.rmtree(tmp)

if __name__ == '__main__':
  sys.exit(0 if main() else 1)
