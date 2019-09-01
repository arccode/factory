#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.tools import download_patch


class CherryPickChangesTest(unittest.TestCase):
  def _BuildCommitObject(self, commit_hash, parent_hash):
    PROJECT_URL = 'project/'
    REVIEW_URL = 'review/'

    return {
        'subject': 'SUBJECT_' + commit_hash,
        'change_id': 'CHANGE_ID_' + commit_hash,
        'parent': parent_hash,
        'fetch': {'url': PROJECT_URL,
                  'ref': 'REF_' + commit_hash},
        'url': REVIEW_URL + commit_hash}

  def assertSubSequence(self, subseq, seq):
    """Asserts that subseq is a subsequence of seq."""

    seq_idx = 0
    for v in subseq:
      found = False
      while seq_idx < len(seq):
        seq_idx += 1
        if v == seq[seq_idx - 1]:
          found = True
          break
      if not found:
        raise AssertionError('%r is not a subsequence of %r' % (subseq, seq))

  def testTopologicalSort(self):
    # a -> b -> c
    changes = {
        'a': self._BuildCommitObject('a', '-'),
        'b': self._BuildCommitObject('b', 'a'),
        'c': self._BuildCommitObject('c', 'b'), }

    changes = download_patch.TopologicalSort(changes)
    self.assertListEqual(
        [v['commit'] for v in changes],
        ['a', 'b', 'c'])

    # a -> b -> c -> e
    #       `-> d
    # f
    # g -> h
    changes = {
        'a': self._BuildCommitObject('a', '-'),
        'b': self._BuildCommitObject('b', 'a'),
        'c': self._BuildCommitObject('c', 'b'),
        'd': self._BuildCommitObject('d', 'b'),
        'e': self._BuildCommitObject('e', 'c'),
        'f': self._BuildCommitObject('f', '-'),
        'g': self._BuildCommitObject('g', '-'),
        'h': self._BuildCommitObject('h', 'g'), }

    changes = download_patch.TopologicalSort(changes)
    ordered_commits = [v['commit'] for v in changes]
    self.assertSubSequence(['a', 'b', 'c', 'e'], ordered_commits)
    self.assertSubSequence(['a', 'b', 'd'], ordered_commits)
    self.assertSubSequence(['g', 'h'], ordered_commits)


if __name__ == '__main__':
  unittest.main()
