#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test proving a fix for strptime Python bug.

Previously, a bug was encountered where strptime would sometimes fail when
used in a new thread for the first time (see http://bugs.python.org/issue7980
for more information).

The fix is to include this import somewhere in the main process before starting
any subthreads:

  import _strptime

This unittest serves as proof that failure will occur without this import, and
that including this import solves the problem.
"""

import datetime
import subprocess
import sys
import threading
import time
import unittest


error = False


def StrptimeRun(strptime, patched):
  """Checks the given strptime function runs without raising an Exception.

  Returns:
    True on success, False on failure.
  """
  if patched:
    import _strptime  # pylint: disable=unused-import

  def Target(fn):
    global error  # pylint: disable=global-statement
    try:
      fn('Tue Aug 16 21:30:00 1988', '%c')
    except AttributeError:
      error = True

  threads = []
  for unused_i in range(2):
    t = threading.Thread(target=Target, args=(strptime,))
    t.start()
    threads.append(t)
  for t in threads:
    t.join()

  return not error


class TestStrptime(unittest.TestCase):

  def _Attempt(self, fn_name, patched):
    retcode = 0
    test_args = [fn_name]
    if patched:
      test_args += ['patched']
    for unused_i in range(20):
      p = subprocess.Popen([sys.executable, sys.argv[0]] + test_args,
                           stderr=subprocess.PIPE)
      p.communicate()
      retcode |= p.returncode
    return not retcode

  @unittest.expectedFailure
  def testUnpatched(self):
    self.assertFalse(self._Attempt('time', False))
    self.assertFalse(self._Attempt('datetime', False))

  def testPatched(self):
    self.assertTrue(self._Attempt('time', True))
    self.assertTrue(self._Attempt('datetime', True))


def main():
  if len(sys.argv) > 1:
    patched = len(sys.argv) > 2 and sys.argv[2] == 'patched'
    fn = None
    if sys.argv[1] == 'time':
      fn = time.strptime
    elif sys.argv[1] == 'datetime':
      fn = datetime.datetime.strptime
    if not fn:
      print('%s: [<time/datetime> [patched]]' % sys.argv[0])
    if fn:
      sys.exit(0 if StrptimeRun(fn, patched) else 1)

  else:
    unittest.main()


if __name__ == '__main__':
  main()
