#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import logging
import os
import re
import shutil
import sys
import tempfile


import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils.process_utils import Spawn, PIPE


def GetDefaultBoardOrNone():
  try:
    return open(os.path.join(os.environ['CROS_WORKON_SRCROOT'],
                             'src', 'scripts', '.default_board')).read().strip()
  except IOError:
    return None


REPOS = {
    'factory': 'platform/factory',
    'board-overlay': 'private-overlays/overlay-%(board)s-private',
    'autotest': 'third_party/autotest/files'
}

MAX_COMMITS = 1000
TEST_LIST_PATH = 'chromeos-base/autotest-private-board/files/test_list'
IN_PLACE = 'IN_PLACE'
MOUNT_POINT = '/tmp/patch_image_mount'

class Repo(object):
  def __init__(self, repo_id, path):
    self.repo_id = repo_id
    self.path = path
    self.affected_paths = set()

class Commit(object):
  def __init__(self, hash, repo, count):  # pylint: disable=W0622
    self.hash = hash
    self.repo = repo
    self.count = count
    self.files = []

  def __repr__(self):
    return 'Commit(%s in %s)' % (self.hash[0:8] + '...', self.repo.repo_id)


def main():
  parser = argparse.ArgumentParser(
      description="Patches a factory image according with particular commits.")
  parser.add_argument('--input', '-i', help='Input image', required=True)
  parser.add_argument('--output', '-o', help='Output image', required=True)
  parser.add_argument('--commits', '--commit', help=(
      'Commit hashes in factory, board overlay, or autotest repository'),
                      action='append', required=True)
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument('--board', help='Board (default: %(default)s)',
                      default=GetDefaultBoardOrNone())
  parser.add_argument('--yes', '-y',
                      help="Don't prompt for confirmation",
                      action='store_true')
  args = parser.parse_args()
  logging.basicConfig(level=logging.INFO - 10 * (args.verbose or 0))

  if not args.board:
    parser.error(
        'No --board argument was specified and no default is available')

  if not os.path.exists(args.input):
    parser.error('Input image %s does not exist' % args.input)
  if args.output != IN_PLACE and os.path.exists(args.output):
    parser.error('Output file %s exists; please remove it first' % args.output)

  # Allow spaces, commas, or colons to separate commits
  args.commits = sum([re.split('[ ,:]', x) for x in args.commits], [])
  args.commits = [x for x in args.commits if x]

  repos = [Repo(k, os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src',
                                v % {'board': args.board}))
           for k, v in sorted(REPOS.items())]

  all_commits = []

  # Get last bunch of commits in each repo in reverse order.  This is
  # necessary to know which revision we should use to fetch all the
  # files that we're going to patch.
  count = 0
  for r in repos:
    for line in Spawn(
        ['git', 'log', '--format=%H', '-%d' % MAX_COMMITS],
        cwd=r.path, check_output=True).stdout_data.strip().split():
      all_commits.append(Commit(line, r, count))
      count += 1

  fail = False
  commits = []
  # Make sure all desired commits are accounted for.
  for commit_hash in args.commits:
    found = [c for c in all_commits
             if c.hash.startswith(commit_hash)]
    if not found:
      logging.error(
          'Unable to find commit %r (is the correct branch checked out?)',
          commit_hash)
      fail = True
    if len(found) > 1:
      logging.error('Ambiguous commit %r (matches %s)', commit_hash, found)
      fail = True

    # Get the subject
    commit = found[0]
    commit.subject = Spawn(['git', 'log', '-1', '--format=%s',
                              commit.hash], check_output=True,
                             cwd=commit.repo.path).stdout_data.strip()

    # Get the list of files
    for f in Spawn(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r',
                    commit.hash], cwd=commit.repo.path,
                   check_output=True).stdout_lines(True):
      commit.files.append(f)
      commit.repo.affected_paths.add(f)
    commits.append(commit)

  if fail:
    parser.exit(1)
  if not commits:
    # Shouldn't happen, but just in case
    parser.exit(1, 'No commits found')

  commits.sort(key=lambda x: x.count)
  for commit in commits:
    logging.info('Found %s: %s', commit, commit.subject)

  # Create staging directory
  staging_dir = tempfile.mkdtemp(prefix='image.')
  os.chmod(staging_dir, 0755)

  # Remove repos with no commits
  repos = [r for r in repos if r.affected_paths]
  for r in repos:
    # Remove ebuild symlinks from affected paths.
    if r.repo_id == 'board-overlay':
      r.affected_paths = set(
          p for p in r.affected_paths
          if not re.search(r'/autotest-private-board-.+-r\d+\.ebuild$', p))

      if r.affected_paths != set([TEST_LIST_PATH]):
        sys.exit('In board-overlay repo, expected only %r in commits but have '
                 'have %s' % (
                     TEST_LIST_PATH, r.affected_paths))

    if r.repo_id == 'factory':
      if 'py/goofy/js/goofy.js' in r.affected_paths:
        sys.exit("Sorry, I can't patch in goofy.js changes.  You'll need to "
                 "build and patch goofy.js yourself.")

    logging.info('In repo %s, affected paths are %s',
                 r.repo_id, sorted(list(r.affected_paths)))

    # Get a copy of the latest checkout, with all the files mentioned
    # in the CL.
    repo_staging_dir = tempfile.mkdtemp(prefix='image.%s.' % r.repo_id)
    logging.info('Staging %s into %s', r.repo_id, repo_staging_dir)

    first_commit = [c for c in commits if c.repo == r][0]
    git = Spawn(['git', 'archive', '--format=tar', first_commit.hash],
                cwd=r.path, stdout=PIPE)
    tar_xf = Spawn(['tar', 'xf', '-'] + list(r.affected_paths),
                   cwd=repo_staging_dir, stdin=git.stdout)

    git.stdout.close()
    if git.wait():
      sys.exit('git failed')
    if tar_xf.wait():
      sys.exit('tar failed')

    RSYNC = ['rsync', '-a', '--chmod=Duga+rx']

    # Now... really stage it.  This is different for each repo.
    if r.repo_id == 'factory':
      dest_dir = os.path.join(staging_dir, 'dev_image', 'factory')
      utils.TryMakeDirs(dest_dir)
      Spawn(RSYNC + [repo_staging_dir + '/', dest_dir + '/'],
            log=True, check_call=True)
    elif r.repo_id == 'autotest':
      # There shouldn't be anything in autotest except for the
      # 'client' directory.
      all_files = os.listdir(repo_staging_dir)
      if all_files != ['client']:
        sys.exit('Expected only client directory to be modified in autotest, '
                 'but other files %r are present too' % all_files)
      dest_dir = os.path.join(staging_dir, 'dev_image', 'autotest')
      utils.TryMakeDirs(dest_dir)
      Spawn(RSYNC + [repo_staging_dir + '/client/', dest_dir + '/'],
            log=True, check_call=True)
    elif r.repo_id == 'board-overlay':
      # There is only one file in this overlay: test_list
      dest_dir = os.path.join(
          staging_dir,
          'dev_image', 'autotest', 'client', 'site_tests', 'suite_Factory')
      utils.TryMakeDirs(dest_dir)
      Spawn(RSYNC + [repo_staging_dir + '/' + TEST_LIST_PATH,
                     dest_dir],
            log=True, check_call=True)
    else:
      sys.exit('Unknown repo ID %s' % r.repo_id)

  # Use root for everything in staging.
  Spawn(['chown', '-R', 'root:root', staging_dir],
        log=True, sudo=True, check_call=True)

  diffs = tempfile.NamedTemporaryFile(prefix='patch_image_diffs.', delete=False)
  with MountPartition(args.input, 1, MOUNT_POINT):
    for f in Spawn(['find', '.', '!', '-type', 'd'],
                   cwd=staging_dir, check_output=True).stdout_lines():
      f = f.strip()[2:]  # Strip and remove './' at beginning
      Spawn(['diff', '-u',
             os.path.join(MOUNT_POINT, f),
             os.path.join(staging_dir, f)],
            stdout=diffs, call=True)
  diffs.close()

  # Do a "find" command to show all affected paths.
  sys.stdout.write(
      ('\n'
       '\n'
       '*** The following files will be patched into the image.\n'
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

  utils.TryMakeDirs(MOUNT_POINT)
  with MountPartition(args.output, 1, MOUNT_POINT, rw=True):
    Spawn(['rsync', '-av', staging_dir + '/', MOUNT_POINT + '/'],
          sudo=True, log=True, check_output=True)


if __name__ == '__main__':
  main()
