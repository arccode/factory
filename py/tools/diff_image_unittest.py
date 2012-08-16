#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import os
import re
import tempfile
import shutil
import sys
import unittest
from StringIO import StringIO

import factory_common  # pylint: disable=W0611
from cros.factory.tools import diff_image

EXPECTED_OUTPUT = '''
*** autotest/different
*** Files differ; unified diff follows
--- $TMPDIR/1/dev_image/autotest/different\t$TIME
+++ $TMPDIR/2/dev_image/autotest/different\t$TIME
@@ -1 +1 @@
-Different: 0
+Different: 1

*** autotest/only-in-autotest
*** Only in image2

*** factory/different-link
*** symlink to 'same-in-both-0' in image1 but 'same-in-both-1' in image2

*** factory/only-in-factory
*** Only in image1

Found 4 differences
'''

class DiffImageTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp(suffix='.diff_image_unittest')
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(sys, 'exit')

    self.images = [os.path.join(self.tmp, str(x))
                   for x in (1, 2)]
    os.mkdir(self.images[0])

    self.dev_image = os.path.join(self.images[0], 'dev_image')
    os.mkdir(self.dev_image)
    self.factory = os.path.join(self.dev_image, 'factory')
    os.mkdir(self.factory)
    self.autotest = os.path.join(self.dev_image, 'autotest')
    os.mkdir(self.autotest)
    with open(os.path.join(self.factory, 'same-in-both-0'), 'w') as f:
      print >> f, 'Same in both 0'
    with open(os.path.join(self.factory, 'same-in-both-1'), 'w') as f:
      print >> f, 'Same in both 1'
    os.symlink('../factory/same-in-both-0',
               os.path.join(self.autotest, 'same-in-both-link'))

    shutil.copytree(self.images[0], self.images[1], symlinks=True)

  def tearDown(self):
    shutil.rmtree(self.tmp)
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testSame(self):
    # No differences yet
    out = StringIO()
    sys.exit(0)
    self.mox.ReplayAll()
    diff_image.main(self.images, out)
    self.assertEquals('\nFound 0 differences\n', out.getvalue())

  def testDifferent(self):
    # OK, now make some differences
    open(os.path.join(self.images[0], 'dev_image', 'factory',
                      'only-in-factory'), 'w').close()
    open(os.path.join(self.images[1], 'dev_image', 'autotest',
                      'only-in-autotest'), 'w').close()

    for i in (0, 1):
      with open(os.path.join(self.images[i], 'dev_image', 'autotest',
                             'different'), 'w') as f:
        print >> f, 'Different: %d' % i
      os.symlink('same-in-both-%i' % i,
                 os.path.join(self.images[i], 'dev_image', 'factory',
                              'different-link'))

    out = StringIO()
    sys.exit(1)
    self.mox.ReplayAll()
    diff_image.main(self.images, out)
    output = out.getvalue()
    # Change temp directory to $TMPDIR in output, since it's different
    # every time.
    output = output.replace(self.tmp, '$TMPDIR')
    # Change times, since they change every time too
    output = re.sub(r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d\.\d+ [\+\-]\d{4}',
                    '$TIME', output)
    self.assertEquals(EXPECTED_OUTPUT, output)

if __name__ == '__main__':
  unittest.main()
