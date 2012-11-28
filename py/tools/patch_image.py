#!/usr/bin/python -Bu
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import logging
import multiprocessing
import os
import re
import shutil
import sys
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils.process_utils import Spawn


FIRMWARE_UPDATE_BINARIES = [
    'crossystem', 'dump_fmap', 'flashrom', 'gbb_utility', 'mosys', 'vpd']


SRC = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src')
def GetDefaultBoardOrNone():
  try:
    return open(os.path.join(SRC, 'scripts', '.default_board')).read().strip()
  except IOError:
    return None

def ParseListArg(value):
  value = sum([re.split('[ ,:]', x) for x in value], [])
  return [x for x in value if x]

def ContentsDiffer(src_path, dest_path):
  """Returns True if the two files differ.

  The files are considered to differ if:

    - Their modes are different.
    - If the files are firmware updaters, and they contain any differing files
      *except* for the binaries listed in FIRMWARE_UPDATE_BINARIES.
    - If the files are not firmware updaters, and they have different contents.
  """
  src_stat = os.stat(src_path)
  dest_stat = os.stat(dest_path)

  if (src_stat.st_mode & ~7) != (dest_stat.st_mode & ~7):
    return True

  if all(os.path.basename(x) == 'chromeos-firmwareupdate'
         for x in (src_path, dest_path)):
    hashes = []
    for p in src_path, dest_path:
      output = Spawn([p, '-V'], log=True, check_output=True).stdout_data
      hash_codes = {}
      for line in output.rpartition('Package Content:')[2].strip().split('\n'):
        hash_code, _, filename = line.rpartition(' *./')
        assert hash_code and filename, (
            'Unable to parse chromeos-firmwareupdate output')
        if filename not in FIRMWARE_UPDATE_BINARIES:
          # Not a binary file; add to the hashes
          hash_codes[filename] = hash_code
      hashes.append(hash_codes)

    logging.info('Firmware hashes: %s', hashes)
    return hashes[0] != hashes[1]
  else:
    return ((src_stat.st_size != dest_stat.st_size) or
            (open(src_path).read() != open(dest_path).read()))

PACKAGES = {
    'factory':
      dict(path='platform/factory',
           package='chromeos-base/chromeos-factory',
           workon=True),
    'chromeos-factory-board':
      dict(path='private-overlays/overlay-%(board)s-private',
           package='chromeos-base/chromeos-factory-board',
           workon=False),
    'autotest-private-board':
      dict(path='private-overlays/overlay-%(board)s-private',
           package='chromeos-base/autotest-private-board',
           workon=False),
    'autotest':
      dict(path='third_party/autotest/files',
           package='chromeos-base/autotest',
           workon=True),
    'autotest-factory':
      dict(path='third_party/autotest/files',
           package='chromeos-base/autotest-factory',
           workon=True),
    }

# A secret value for 'output' to make the script modify the image in place.
# Only for testing.
IN_PLACE = 'IN_PLACE'
OLD_IMAGE_MOUNT_POINT = '/tmp/old_image_mount'
NEW_IMAGE_MOUNT_POINT = '/tmp/new_image_mount'
ALL = 'ALL'

def main():
  parser = argparse.ArgumentParser(
      description="Patches a factory image according with particular commits.")
  parser.add_argument('--input', '-i', help='Input image', required=True)
  parser.add_argument('--output', '-o', help='Output image', required=True)
  parser.add_argument('--output-updater', help='Output factory.tar.bz2')
  parser.add_argument('--branch', '-b',
                      help='Branch to patch (e.g., factory-2848.B or HEAD)',
                      required=True)
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument('--packages', '--package',
                      help=('Packages to patch in (%s, or '
                            'one or more of [%s])' % (
                                ALL, ','.join(sorted(PACKAGES.keys())))),
                      action='append', required=True)
  parser.add_argument('--board', help='Board (default: %(default)s)',
                      default=GetDefaultBoardOrNone())
  parser.add_argument('--no-clean', action='store_false', dest='clean',
                      help="Don't insist on clean repositories (be careful!)")
  parser.add_argument('--no-emerge', action='store_false', dest='emerge',
                      help="Don't emerge (for debugging only)")
  parser.add_argument('--no-sync', action='store_false', dest='sync',
                      help="Don't emerge (for debugging only)")
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")
  args = parser.parse_args()
  logging.basicConfig(level=logging.INFO - 10 * (args.verbose or 0))

  if not args.board:
    parser.error(
        'No --board argument was specified and no default is available')

  if not os.path.exists(args.input):
    parser.error('Input image %s does not exist' % args.input)
  if args.output != IN_PLACE and os.path.exists(args.output):
    parser.error('Output file %s exists; please remove it first' % args.output)

  args.output_updater = (
      args.output_updater or
      os.path.join(os.path.dirname(os.path.realpath(args.output)),
                   'factory.tar.bz2'))
  if os.path.exists(args.output):
    parser.error('Output update file %s exists; please remove it first' %
                 args.output_updater)

  args.packages = set(ParseListArg(args.packages))

  if ALL in args.packages:
    args.packages = set(PACKAGES.keys())
  bad_packages = args.packages - set(PACKAGES.keys())
  if bad_packages:
    parser.error('Bad packages %s (should be in %s)' % (
        list(bad_packages), sorted(PACKAGES.keys())))

  repo_relpaths = [PACKAGES[k]['path'] % {'board': args.board}
                   for k in args.packages]
  repo_paths = sorted(set([os.path.join(SRC, x) for x in repo_relpaths]))
  packages = sorted(set(PACKAGES[k]['package'] for k in args.packages))
  workon_packages = sorted(set(PACKAGES[k]['package']
                               for k in args.packages
                               if PACKAGES[k]['workon']))

  # Check the packages are all clean
  for path in repo_paths:
    stdout = Spawn(['git', 'status', '--ignored', '--porcelain'],
                   cwd=path, check_output=True).stdout_data
    if stdout:
      logging.error('Repository %s is not clean:\n%s', path, stdout)
      if args.clean:
        logging.error('To clean it (but be careful!):\n\n'
                      '( cd %s && git clean -xdf )', path)
        sys.exit(1)

  # Check out the appropriate branch in each repo
  for path in repo_paths:
    if args.branch.startswith('factory-'):
      branch = (('cros-internal/' if path.endswith('-private') else 'cros/')
                + args.branch)
    else:
      branch = args.branch
    Spawn(['git', 'checkout', branch], cwd=path, log=True, check_call=True)

  # Do workons
  if workon_packages:
    Spawn(['cros_workon', 'start'] + workon_packages, log=True, call=True)

  # Do repo syncs in parallel (followed by a rebase+sync if it fails)
  if args.sync:
    for i, process in enumerate(
        [Spawn('repo sync . || (repo rebase . && repo sync .)',
               log=True, cwd=path, shell=True) for path in repo_paths]):
      if process.wait() != 0:
        sys.exit('git fetch in %s failed' % repo_paths[i])

    for path in repo_paths:
      process = Spawn(['repo', 'rebase', '.'], read_stderr=True,
                      cwd=path, log=True, call=True)
      if process.wait() != 0:
        if (process.returncode == 255 and
            re.search('has a detat?ched HEAD', process.stderr_data)):
          pass
        else:
          sys.exit('repo rebase in %s failed' % path)

  # If there are any autotest packages required, unmerge them all so that
  # any old packages don't get in the way.  There's probably a better way
  # to do this.
  if [x for x in args.packages if x.startswith('autotest')]:
    Spawn('emerge-link --unmerge $(cros_workon list --all | grep autotest)',
          log=True, shell=True, check_call=True)

  # Emerge the packages
  tarballs = []

  if args.emerge:
    Spawn(['emerge-%s' % args.board, '--buildpkg',
           '-j', str(multiprocessing.cpu_count())] +
          packages,
          log=True, check_call=True)

  for package in packages:
    ebuild = Spawn(
        ['equery-%s' % args.board, 'w', package],
        check_output=True).stdout_data.strip()
    tarball = os.path.join(
        '/build', args.board, 'packages',
        os.path.dirname(package),
        os.path.basename(ebuild).replace('.ebuild', '.tbz2'))
    logging.info('%s %s (%d bytes)', 'Built' if args.emerge else 'Reusing',
                 tarball, os.path.getsize(tarball))
    tarballs.append(tarball)

  # Create staging directory
  staging_dir = tempfile.mkdtemp(prefix='new-image.')
  os.chmod(staging_dir, 0755)

  # Create the /usr/local/factory/custom symlink.
  factory_dir = os.path.join(staging_dir, 'usr', 'local', 'factory')
  utils.TryMakeDirs(factory_dir)
  os.symlink('../autotest/client/site_tests/suite_Factory',
             os.path.join(factory_dir, 'custom'))

  # Unpack tarballs to staging directory
  for t in tarballs:
    Spawn(['tar', 'xfj', t, '-C', staging_dir],
          check_call=True, log=True)

  # Apply install mask
  install_mask = Spawn(
      ['source %s && echo "$FACTORY_TEST_INSTALL_MASK"' %
       os.path.join(SRC, 'scripts', 'common.sh')],
      shell=True, check_output=True, log=True).stdout_data.strip().split()
  for f in install_mask:
    # Use shell to expand glob since Python's globbing is a bit stupid
    assert not re.search(r'\s', f)
    Spawn(['shopt -s nullglob; rm -rf %s/%s' % (staging_dir, f)],
          shell=True, check_call=True)

  # Move /usr/local/factory to dev_image.
  dev_image = os.path.join(staging_dir, 'dev_image')
  os.mkdir(dev_image)
  path = os.path.join(staging_dir, 'usr', 'local', 'factory')
  if os.path.exists(path):
    shutil.move(path, dev_image)
  # Move /usr/local/autotest/client to /usr/local/autotest.
  path = os.path.join(staging_dir, 'usr', 'local', 'autotest', 'client')
  if os.path.exists(path):
    shutil.move(path, os.path.join(dev_image, 'autotest'))

  # Delete usr and var directories
  for f in ['usr', 'var']:
    path = os.path.join(staging_dir, f)
    if os.path.exists(path):
      shutil.rmtree(path)

  diffs = tempfile.NamedTemporaryFile(prefix='patch_image.diff.',
                                      delete=False)

  # Find and remove identical files to avoid massive mtime changes.
  utils.TryMakeDirs(OLD_IMAGE_MOUNT_POINT)
  with MountPartition(args.input, 1, OLD_IMAGE_MOUNT_POINT):
    for root, dirs, files in os.walk(staging_dir):
      for is_dir in [False, True]:
        for f in dirs if is_dir else files:
          path = os.path.join(root, f)
          assert path.startswith(staging_dir + '/')
          rel_path = os.path.relpath(path, staging_dir)
          dest_path = os.path.join(OLD_IMAGE_MOUNT_POINT, rel_path)

          if not os.path.exists(dest_path):
            diffs.write('*** File %s does not exist in old image\n' % rel_path)
            continue

          src_islink = os.path.islink(path)
          dest_islink = os.path.islink(dest_path)
          if src_islink != dest_islink:
            continue
          if src_islink:
            if os.readlink(path) == os.readlink(dest_path):
              # They are identical.  No need to rsync; delete it.
              os.unlink(path)
            continue

          if is_dir:
            continue

          if f in ['.keep', 'chromedriver']:
            # Just to tell Gentoo to keep the directory; delete it
            os.unlink(path)
            continue

          if ContentsDiffer(path, dest_path):
            # They are different; write a diff
            Spawn(['diff', '-u', dest_path, path], stdout=diffs, call=True)
          else:
            # They are identical.  No need to rsync; delete the src file.
            os.unlink(path)

  # Delete empty directories in dev_image
  for root, dirs, files in os.walk(dev_image, topdown=False):
    for d in dirs:
      try:
        os.rmdir(os.path.join(root, d))
      except OSError:
        pass  # Not empty, no worries

  diffs.close()
  # Do a "find" command to show all affected paths.
  sys.stdout.write(
      ('\n'
       '\n'
       '*** The following changes files will be patched into the image.\n'
       '***\n'
       '*** Note that the individual changes that you mentioned will not\n'
       '*** be cherry-picked; rather the LATEST VERSION of the file in the\n'
       '*** LATEST TREE you specified on the command line will be chosen.\n'
       '***\n'
       '*** DISCLAIMER: This script is experimental!  Make sure to\n'
       '*** double-check that all the changes you expect are really included!\n'
       '***\n'
       '\n'
       'cd %s\n'
       '\n'
       '%s'
       '\n'
       '*** Diffs are available in %s\n'
       '*** Check them carefully!\n'
       '***\n') %
      (staging_dir,
       Spawn('find . ! -type d -print0 | xargs -0 ls -ld',
             cwd=staging_dir, shell=True,
             check_output=True).stdout_data,
       diffs.name))

  if not args.yes:
    sys.stdout.write('*** Is this correct? [y/N] ')
    answer = sys.stdin.readline()
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')

  if args.output == IN_PLACE:
    logging.warn('Modifying image %s in place! Be very afraid!', args.input)
    args.output = args.input
  else:
    logging.info('Copying %s to %s', args.input, args.output)
    shutil.copyfile(args.input, args.output)

  utils.TryMakeDirs(NEW_IMAGE_MOUNT_POINT)
  with MountPartition(args.output, 1, NEW_IMAGE_MOUNT_POINT, rw=True):
    Spawn(['rsync', '-av', staging_dir + '/', NEW_IMAGE_MOUNT_POINT + '/'],
          sudo=True, log=True, check_output=True)

  logging.info('\n'
               '***\n'
               '*** Created %s (%d bytes)\n'
               '***', args.output, os.path.getsize(args.output))

  Spawn([os.path.join(os.path.dirname(os.path.realpath(__file__)),
                      'make_update_bundle.py'),
         '-i', args.output, '-o', args.output_updater],
        log=True, check_call=True)

if __name__ == '__main__':
  main()
