#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.state import PathResolver


class PathResolverTest(unittest.TestCase):

  def testWithRoot(self):
    resolver = PathResolver()
    resolver.AddPath('/', '/root')
    resolver.AddPath('/a/b', '/c/d')
    resolver.AddPath('/a', '/e')

    for url_path, expected_local_path in (
        ('/', '/root'),
        ('/a/b', '/c/d'),
        ('/a', '/e'),
        ('/a/b/X', '/c/d/X'),
        ('/a/X', '/e/X'),
        ('/X', '/root/X'),
        ('/X/', '/root/X/'),
        ('/X/Y', '/root/X/Y'),
        ('Blah', None)):
      self.assertEqual(expected_local_path,
                       resolver.Resolve(url_path))

  def testNoRoot(self):
    resolver = PathResolver()
    resolver.AddPath('/a/b', '/c/d')
    self.assertEqual(None, resolver.Resolve('/b'))
    self.assertEqual('/c/d/X', resolver.Resolve('/a/b/X'))

if __name__ == '__main__':
  unittest.main()
