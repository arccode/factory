#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
A script to diff master branch and factory branch. It shows the commits that
only in master branch or only in factory branch.

By default, these repos are diff'ed:
  platform/factory
  platform/chromeos-hwid

If a board is specified, the private overlay repo for that board is also
included. In this case, if branch is not specified, this script tries to find
the latest factory-<board>-*.B branch.
"""

import argparse
from collections import namedtuple
import glob
import logging
import os
import re
import subprocess
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import CheckOutput, Spawn
from cros.factory.tools import build_board

DiffEntry = namedtuple('DiffEntry',
                       ['left_right', 'hash', 'author', 'subject'])

COLOR_RESET = '\033[0m'
COLOR_YELLOW = '\033[33m'
COLOR_CYAN = '\033[36m'
COLOR_GREEN = '\033[1;32m'

CHERRY_PICK = 'CHERRY-PICK: '

PRIVATE_OVERLAY_LIST = ['src/private-overlays/overlay-%s-private',
                        'src/private-overlays/overlay-variant-*-%s-private']

FACTORY_REPO_LIST = ['src/platform/factory', 'src/platform/chromeos-hwid']

# Please add the repo if you think it is important in factory.
OTHER_REPO_LIST = ['src/platform/touch_updater', 'src/platform/mosys',
                   'src/platform/factory_installer', 'src/platform/ec',
                   'src/third_party/autotest/files',
                   'src/third_party/xf86-video-armsoc', 'src/third_party/adhd',
                   'src/third_party/chromiumos-overlay']

# The kernel repo has several different versions. The actual kernel version will
# be determined during runtime based on the board name provided.
KERNEL_REPO_PATTERN = 'src/third_party/kernel/%(version)s'

# m/master does not point to cros/master in the repo in this list. We can only
# know where it points to if the tree was inited without -b and has
# m/master branch.
DIFFERENT_MASTER_REPO_LIST = glob.glob('src/third_party/kernel/*')

# Repo in this list like 'src/third_party/chromiumos-overlay' does not contain
# other branches by default. 'git fetch cros' can fetch all the branches.
# 'git fetch cros <factory_branch>' can fetch specified factory branch.
# However, repo sync will not update those fetched branches for you,
# so we have to force fetching the branch each time we want to diff.
FORCE_FETCH_REPO_LIST = ['src/third_party/chromiumos-overlay']


SRC = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src')
def GetDefaultBoardOrNone():
  try:
    return (open(os.path.join(SRC, 'scripts', '.default_board')).read()
            .strip().rpartition('_')[2])
  except IOError:
    return None

def GetFullRepoPath(repo_path):
  """Returns the full path of the given repo."""
  return os.path.join(os.path.expanduser('~'), 'trunk', repo_path)


def FindGitPrefix(repo_path):
  """Gets Git prefix, either 'cros' or 'cros-internal'."""
  os.chdir(GetFullRepoPath(repo_path))
  branch_list = CheckOutput(['git', 'branch', '-av'])
  for line in reversed(branch_list.split('\n')):
    match = re.search('remotes\/([^/]*)/[^/]*', line)
    if match and match.group(1) != 'm':
      return match.group(1)
  return None



def GetBranch(board):
  """Gets latest factory branch for a board."""
  if not board:
    return None

  os.chdir(GetFullRepoPath('src/platform/factory'))
  branch_list = CheckOutput(['git', 'branch', '-av'])
  for line in reversed(branch_list.split('\n')):
    match = re.search('remotes\/cros\/(factory-%s-\d+.B)' % board, line)
    if match:
      return match.group(1)
  return None


def GetPrivateOverlay(board):
  """Gets the path to private overlay."""
  for pattern in PRIVATE_OVERLAY_LIST:
    path = glob.glob(GetFullRepoPath(pattern % board))
    if path:
      if len(path) > 1:
        logging.warning('Found more than one private overlays:\n%s',
                        '\n'.join(path))
      return path[0]
  return None


def GetBoardKernelVersion(board):
  """Gets the kernel version used by the given board."""
  KERNEL_SRC_USE_RE = re.compile(r'\+kernel-(\d+_\d+)', re.MULTILINE)
  return KERNEL_SRC_USE_RE.search(
      CheckOutput(['equery-%s' % board, 'uses', 'linux-sources'])
      ).group(1).replace('_', '.')


def GetDiffList(diff):
  """Generates a list of DiffEntry from Git output.

  Args:
    diff: The output from Git log command.

  Returns:
    A list of DiffEntry. Each DiffEntry corresponds to a commit that
      is in one branch.
  """
  ret = []
  for line in diff.split('\n'):
    match = re.match('([<>]) ([0-9a-f]+) \(([^\)]+)\) (.*)', line)
    if match:
      if match.group(4) == 'Marking set of ebuilds as stable':
        continue
      ret.append(DiffEntry(*match.groups()))

  return ret


def RemoveCherryPickPrefix(subject):
  return (subject[len(CHERRY_PICK):]
          if subject.startswith(CHERRY_PICK)
          else subject)


def RemoveCherryPick(diff_list):
  diffed = {'<': set(), '>': set()}

  for entry in diff_list:
    subject = RemoveCherryPickPrefix(entry.subject)
    diffed[entry.left_right].add((entry.author, subject))

  # If a commit shows up in both branches, it is cherry-picked.
  # (Even though Git doesn't know they are the same.)
  cherrypicked = diffed['<'] & diffed['>']

  return [entry for entry in diff_list
          if (entry.author, RemoveCherryPickPrefix(entry.subject))
          not in cherrypicked]


def RefExist(repo_path, full_branch_name):
  """Checks if there exists a reference named full_branch_name."""
  os.chdir(GetFullRepoPath(repo_path))
  cmd = ['git', 'show-ref', '--verify',
         'refs/remotes/%s' % full_branch_name]
  try:
    Spawn(cmd, check_call=True, ignore_stdout=True, ignore_stderr=True)
  except subprocess.CalledProcessError:
    logging.warning('ref %s does not exist in %s', full_branch_name, repo_path)
    return False
  return True


def BranchExist(repo_path, full_branch_name):
  """Checks if there exists a branch named full_branc_name."""
  os.chdir(GetFullRepoPath(repo_path))
  branch_list = CheckOutput(['git', 'branch', '-av'])
  for line in reversed(branch_list.split('\n')):
    # Matches for <local_branch_name>
    match = re.search(r'\s*(\S*)\s*', line)
    if match and match.group(1) == full_branch_name:
      return True
    # Matches for remotes/<prefix>/<branch_name>
    match = re.search(r'\s*remotes\/(\S*)\s*', line)
    if match and match.group(1) == full_branch_name:
      return True
  logging.warning('branch %s does not exist in %s', full_branch_name, repo_path)
  return False


def FetchBranch(repo_path, prefix, branch, local_branch_name):
  """Fetches reference prefix/branch to fetched ref named local_branch_name."""
  logging.warning('Fetching branch %s/%s to %s for repo %s',
                  prefix, branch, local_branch_name, repo_path)
  os.chdir(GetFullRepoPath(repo_path))
  # Removes old branch.
  if BranchExist(repo_path, local_branch_name):
    cmd = ['git', 'branch', '-D', local_branch_name]
    Spawn(cmd, call=True)
  cmd = ['git', 'fetch', prefix, '%s:%s' % (branch, local_branch_name)]
  Spawn(cmd, check_call=True)


def DiffRepo(repo_path, args, init_with_master):
  print '%s*** Diff %s ***%s' % (COLOR_GREEN, repo_path, COLOR_RESET)
  os.chdir(GetFullRepoPath(repo_path))
  prefix = FindGitPrefix(repo_path)

  # If the tree is not init with master branch, we can only guess m/master is
  # cros/master or cros-internal/master
  master_branch_prefix = 'm' if init_with_master else prefix
  master_branch = master_branch_prefix + '/master'
  compare_branch = prefix + '/' + args.branch
  if (repo_path == (KERNEL_REPO_PATTERN % dict(
      version=GetBoardKernelVersion(args.board.full_name)))):
    # The kernel repo has a slightly different branch naming. There is a
    # '-chromeos-<kernel_version>' suffix after the branch name.
    compare_branch += '-chromeos-%s' % GetBoardKernelVersion(
        args.board.full_name)

  # Force fetching for if repo is in FORCE_FETCH_REPO_LIST.
  # When fetching for the branch, prefix can only be 'cros' or 'cros-internal'.
  if repo_path in FORCE_FETCH_REPO_LIST:
    FetchBranch(repo_path, prefix, 'master', 'TEMP_MASTER')
    FetchBranch(repo_path, prefix, args.branch, 'TEMP_COMPARE')
    master_branch, compare_branch = 'TEMP_MASTER', 'TEMP_COMPARE'

  # Repo not in FORCE_FECH_REPO_LIST should contain both branches.
  elif not (BranchExist(repo_path, master_branch) and
            BranchExist(repo_path, compare_branch)):
    logging.error('%s does not contain both %s and %s, you should add this '
                  'repo to FORCE_FETCH_REPO_LIST', repo_path, master_branch,
                  compare_branch)

  cmd = ['git', 'log', '--cherry-pick', '--oneline', '--left-right',
         '--pretty=format:%m %h (%an) %s',
         '%s...%s' % (master_branch, compare_branch)]
  if args.author:
    cmd += ['--author', args.author]
  diff = CheckOutput(cmd)

  diff_list = GetDiffList(diff)
  diff_list = RemoveCherryPick(diff_list)

  # Show branch name. (e.g. [4131.B])
  branch_name = '[%s]' % args.branch[-6:]

  # To make branch stands out, we only show [------] for commits that
  # are on ToT.
  for entry in diff_list:
    if args.factory_only and entry.left_right == '<':
      continue
    if args.master_only and entry.left_right == '>':
      continue
    print '%s%s %s%s %s %s(%s)%s' % (COLOR_YELLOW,
                                     '[------]' if entry.left_right == '<'
                                     else branch_name,
                                     entry.hash,
                                     COLOR_RESET,
                                     entry.subject,
                                     COLOR_CYAN,
                                     entry.author,
                                     COLOR_RESET)

  print ''


def main():
  parser = argparse.ArgumentParser(
      description=('List the commits that are only in one of master '
                   'and factory branch.'))
  parser.add_argument('--branch', '-r', default=None,
                      help='name of the factory branch')
  parser.add_argument('--board', '-b', default=None,
                      help='board name')
  parser.add_argument('--author', '-a', default=None,
                      help='Limit the output to this author only')
  parser.add_argument('--factory_only', '-o', action='store_true',
                      help='Only show commits on factory branch')
  parser.add_argument('--master_only', '-m', action='store_true',
                      help='Only show commits on ToT')
  parser.add_argument('--show_other_repos', '-s', action='store_true',
                      help='Show commits in OTHER_REPO_LIST as well')
  args = parser.parse_args()

  args.board = args.board or GetDefaultBoardOrNone()
  if args.board:
    args.board = build_board.BuildBoard(args.board)

  if not args.branch:
    args.branch = GetBranch(args.board.short_name)
  if not args.branch:
    logging.error('Cannot determine factory branch name. '
                  'Specify --branch to continue.')
    sys.exit(1)

  repo_list = FACTORY_REPO_LIST
  if args.show_other_repos:
    repo_list += OTHER_REPO_LIST
    # Add the active kernel repo of the give board into list.
    repo_list += [KERNEL_REPO_PATTERN %
                  dict(version=GetBoardKernelVersion(args.board.full_name))]

  if args.board:
    repo_list.append(GetPrivateOverlay(args.board.short_name))

  if RefExist('src/platform/factory', 'm/master'):
    init_with_master = True
  else:
    logging.warning('This tree was inited with -b <branch_name> so there is '
                    'no clue where m/master might point to.')
    logging.warning('Removing repo in %s from repo_list',
                    DIFFERENT_MASTER_REPO_LIST)
    repo_list = [x for x in repo_list if x not in DIFFERENT_MASTER_REPO_LIST]
    init_with_master = False

  if args.factory_only and args.master_only:
    logging.warning('Both --factory_only and --master_only specified. '
                    'Ignoring both.')
    args.factory_only = False
    args.master_only = False

  for repo in repo_list:
    DiffRepo(repo, args, init_with_master)
  sys.exit(0)

if __name__ == '__main__':
  main()
