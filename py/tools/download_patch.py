#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Download patches from gerrit.

This tool will first checkout BRANCH, and cherry-pick changes on gerrit with
specific topic or hashtag.  If BOARD is given, will also cherry-pick changes in
private overlay.
"""


import argparse
import logging
import os
import subprocess
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils import process_utils


try:
  sys.path.append('/mnt/host/depot_tools')
  import gerrit_util  # pylint: disable=import-error
except ImportError:
  logging.exception('cannot find module gerrit_util, which should be found '
                    'under /mnt/host/depot_tools, are you in chroot?')
  raise


def GetFactoryRepoInfo(options):
  return {
      'url': 'chromium-review.googlesource.com',
      'project': 'chromiumos/platform/factory',
      'dir': paths.FACTORY_PATH,
      'branch': 'cros/' + options.branch}


def GetBoardRepoInfo(options):
  board = options.board

  ebuild_path = process_utils.SpawnOutput(
      ['equery-' + board, 'which', 'factory-board'])
  if not ebuild_path:
    logging.warning('cannot find ebuild for factory-board, '
                    'rollback to chromeos-factory-board')
    ebuild_path = process_utils.SpawnOutput(
        ['equery-' + board, 'which', 'chromeos-factory-board'])

  if not ebuild_path:
    raise RuntimeError('cannot find private overlay for board: ' + board)

  overlay_dir = os.path.dirname(ebuild_path)

  # expected output would be like:
  #
  #   Manifest branch: ...
  #   Manifest merge branch: ...
  #   Manifest groups: ...
  #   ----------------------------
  #   Project: chromeos/overlays/overlay-*-private
  #   Mount path: /mnt/host/source/src/private-overlays/*
  #   Current revision: ...
  #   Local Branches: ...
  #   ----------------------------
  #
  PROJECT_LINE_PREFIX = 'Project: '
  repo_info = process_utils.CheckOutput(['repo', 'info', '.'], cwd=overlay_dir)
  project = [s for s in repo_info.splitlines()
             if s.startswith(PROJECT_LINE_PREFIX)][0]  # find project line
  project = project[len(PROJECT_LINE_PREFIX):]  # remove prefix

  return {
      'url': 'chrome-internal-review.googlesource.com',
      'project': project,
      'dir': overlay_dir,
      'branch': 'cros-internal/' + options.branch}


def QueryChanges(info, options):
  """Fetch list of changes with specific topic and branch.

  Args:
    info: required information for the repo we are working on, should be the
      value returned by `GetFactoryRepoInfo` or `GetBoardRepoInfo`.
    options: parsed command line argument.
  """
  param = {
      'project': info['project'],
      'status':'open',
  }
  if options.branch:
    param['branch'] = options.branch
  if options.topic:
    param['topic'] = options.topic
  if options.hashtag:
    param['hashtag'] = options.hashtag

  logging.debug('query change list from gerrit: ')
  logging.debug('  url: %s', info['url'])
  logging.debug('  param: %r', param)

  results = list(
      gerrit_util.GenerateAllChanges(
          info['url'],
          param,
          o_params=['CURRENT_REVISION', 'CURRENT_COMMIT', ]))
  changes = {}

  for change in results:
    current_revision_hash = change['current_revision']
    current_revision = change['revisions'][current_revision_hash]
    changes[current_revision_hash] = {
        'subject': change['subject'],
        'change_id': change['change_id'],
        'parent': current_revision['commit']['parents'][0]['commit'],
        'fetch': current_revision['fetch']['http'],
        'url': 'https://%s/%d' % (info['url'],
                                  change['_number']), }
  return changes


def TopologicalSort(changes):
  """Sort changes in topological order.

  Args:
    changes: a dictionary, which maps commit hashes to commit objects::

        {
          '<commit hash>': {
            'subject': '<subject>',
            'change_id': '<gerrit change ID>',
            'parent': '<parent commit hash>',
            'fetch': {'url': '<url of the project>',
                      'ref': '<ref of the patch set>'},
            'url': '<link to review change>',
          },
        }

    :type changes: dict
  Returns:
    A list of dict objects, each object contains the following attributes::

        {
          'commit': '<commit hash>',
          'url': '<link to review change>',
          'fetch': {'url': '<url of the project>',
                    'ref': '<ref of the patch set>'},
          'subject': '<subject>',
        }
  """
  not_root = set()
  for key in changes.keys():
    parent = changes[key]['parent']
    if parent in changes.keys():
      parent = changes[parent]
      if 'kids' not in parent:
        parent['kids'] = {key: changes[key]}
      else:
        parent['kids'][key] = changes[key]
      not_root.add(key)
  changes = {key: changes[key] for key in set(changes) - not_root}

  # sort CLs in topological order
  def walk(d):
    for k, v in d.iteritems():
      yield {
          'url': v['url'],
          'fetch': v['fetch'],
          'subject': v['subject'],
          'commit': k}
      if 'kids' in v:
        for change in walk(v['kids']):
          yield change
  return list(walk(changes))


def CherryPickChanges(info, changes):
  """Cherry-pick a list of changes.

  Would try to respect dependencies between each changes, that is, will download
  changes in topological order.

  Args:
    info: required information for the repo we are working on, should be the
      value returned by `GetFactoryRepoInfo` or `GetBoardRepoInfo`.
    changes: a dictionary, which maps commit hashes to commit objects::
      {
        '<commit hash>': {
          'subject': '<subject>',
          'change_id': '<gerrit change ID>',
          'parent': '<parent commit hash>',
          'fetch': {'url': '<url of the project>',
                    'ref': '<ref of the patch set>'},
          'url': '<link to review change>',
        },
      }
    :type changes: dict
  """
  changes = TopologicalSort(changes)
  last_success = -1

  try:
    process_utils.LogAndCheckCall(
        ['git', 'checkout', info['branch']],
        cwd=info['dir'])
  except subprocess.CalledProcessError:
    logging.exception('failed to checkout branch %s', info['branch'])
  else:
    for idx, change in enumerate(changes):
      print 'cherry-picking %s...' % change['url']
      try:
        process_utils.LogAndCheckCall(
            ['git', 'fetch', change['fetch']['url'], change['fetch']['ref']],
            cwd=info['dir'])
        process_utils.LogAndCheckCall(
            ['git', 'cherry-pick', 'FETCH_HEAD'],
            cwd=info['dir'])
        last_success = idx
      except subprocess.CalledProcessError:
        logging.exception('failed to cherry pick %s', change['url'])
        break

  print
  print
  print "Summary:"
  for idx, change in enumerate(changes):
    print '%s: %s' % (change['url'],
                      'success' if idx <= last_success else 'failed')
  print
  print


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--topic',
                      help='limit to specific topic')
  parser.add_argument('--hashtag',
                      help='search changes with this hashtag')
  parser.add_argument('--branch', default='master',
                      help='limit to specific branch')
  parser.add_argument('--board',
                      help='board name (to specify the private overlay)')
  parser.add_argument('-v', '--verbose',
                      help='verbose mode', action='store_true')

  options = parser.parse_args()

  logging_level = logging.DEBUG if options.verbose else logging.WARNING
  logging.basicConfig(
      format=('[%(levelname)s] %(filename)s:%(lineno)d: %(message)s'),
      level=logging_level)

  if not options.topic and not options.hashtag:
    logging.error('At least one of --topic and --hashtag must be specified')
    parser.print_usage()
    return

  info = GetFactoryRepoInfo(options)
  changes = QueryChanges(info, options)
  CherryPickChanges(info, changes)

  if options.board:
    info = GetBoardRepoInfo(options)
    changes = QueryChanges(info, options)
    CherryPickChanges(info, changes)


if __name__ == '__main__':
  main()
