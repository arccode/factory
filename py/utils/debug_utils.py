# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import signal
import sys
import traceback


def AddDebugHook():
  '''Adds a signal handler for USR2 to print debug information on SIGUSR2.

  Currently prints all threads' stack traces to stderr.
  '''
  def Handler(dummy_sig, dummy_frame):
    sys.stderr.write(
        '*****\n'
        '*\n'
        '* Caught SIGUSR2.  Dumping debug information.\n'
        '*\n'
        '*****\n')

    # pylint: disable=W0212
    for thread_id, stack in sys._current_frames().items():
      sys.stderr.write('Thread ID %s:' % thread_id)
      for filename, line_no, function_name, text in (
          traceback.extract_stack(stack)):
        # Same format as the usual Python stack trace, but indented
        # twice
        sys.stderr.write('  File: "%s", line %d, in %s\n' % (
            filename, line_no, function_name))
        if text:
          sys.stderr.write('    %s\n' % text.strip())

    sys.stderr.write('***** End of debug information.\n')

  signal.signal(signal.SIGUSR2, Handler)
