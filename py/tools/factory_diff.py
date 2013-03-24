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
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import CheckOutput

DiffEntry = namedtuple('DiffEntry',
                       ['left_right', 'hash', 'author', 'subject'])

COLOR_RESET = '\033[0m'
COLOR_YELLOW = '\033[33m'
COLOR_CYAN = '\033[36m'
COLOR_GREEN = '\033[1;32m'

CHERRY_PICK = 'CHERRY-PICK: '

PRIVATE_OVERLAY_LIST = ['src/private-overlays/overlay-%s-private',
                        'src/private-overlays/overlay-variant-*-%s-private']

REPO_LIST = ['src/platform/factory', 'src/platform/chromeos-hwid']

def GetFullRepoPath(repo_path):
  """Returns the full path of the given repo."""
  return os.path.join(os.path.expanduser('~'), 'trunk', repo_path)


def FindGitPrefix(repo_path):
  """Gets Git prefix, either 'cros' or 'cros-internal'."""
  os.chdir(GetFullRepoPath(repo_path))
  branch_list = CheckOutput(['git', 'branch', '-av'])
  for line in reversed(branch_list.split('\n')):
    match = re.search('remotes\/m\/master\s+-> ([^/]*)/master', line)
    if match:
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


def DiffRepo(repo_path, branch):
  print '%s*** Diff %s ***%s' % (COLOR_GREEN, repo_path, COLOR_RESET)
  os.chdir(GetFullRepoPath(repo_path))

  diff = CheckOutput(['git', 'log', '--cherry-pick', '--oneline',
                      '--left-right', '--pretty=format:%m %h (%an) %s',
                      'm/master...%s/%s' % (FindGitPrefix(repo_path), branch)])

  diff_list = GetDiffList(diff)
  diff_list = RemoveCherryPick(diff_list)

  # To make [Master] stands out, we only show [------] for commits that
  # are in factory branch.
  for entry in diff_list:
    print '%s%s %s%s %s %s(%s)%s' % (COLOR_YELLOW,
                                     '[Master]' if entry.left_right == '<'
                                     else '[------]',
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
  args = parser.parse_args()
  if not args.branch:
    args.branch = GetBranch(args.board)
  if not args.branch:
    logging.error('Cannot determine factory branch name. '
                  'Specify --branch to continue.')
    sys.exit(1)

  for repo in REPO_LIST:
    DiffRepo(repo, args.branch)
  if args.board:
    DiffRepo(GetPrivateOverlay(args.board), args.branch)
  sys.exit(0)

if __name__ == '__main__':
  main()
