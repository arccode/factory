# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import signal
import sys
import traceback


def AddDebugHook():
  '''Adds a signal handler for USR2 to print debug information on SIGUSR2.

  Currently just prints the stack trace of the active thread to stderr.
  '''
  def Handler(dummy_sig, frame):
    sys.stderr.write(
        '*****\n'
        '*\n'
        '* Caught SIGUSR2.  Dumping debug information.\n'
        '*\n'
        '*****\n'
        'Stack trace of active thread:\n')
    traceback.print_stack(frame)
    print >> sys.stderr, '***** End of debug information.'

  signal.signal(signal.SIGUSR2, Handler)
