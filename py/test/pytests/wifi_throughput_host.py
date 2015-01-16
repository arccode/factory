# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WiFi throughput test host script.

Starts iperf3 server, until server exhibits client-timeout behaviour.
Example output::

  Accepted connection from 127.0.0.1, port 60198
  [  5] local 127.0.0.1 port 5201 connected to 127.0.0.1 port 60199
  [ ID] Interval           Transfer     Bandwidth
  [  5]   0.00-1.00   sec  4.41 GBytes  37.9 Gbits/sec
  [  5]   1.00-2.00   sec  5.24 GBytes  45.0 Gbits/sec
  [  5]   2.00-3.00   sec  1.60 GBytes  13.7 Gbits/sec
  [  5]   3.00-4.00   sec  0.00 Bytes  0.00 bits/sec
  [  5]   4.00-5.00   sec  0.00 Bytes  0.00 bits/sec
  [  5]   5.00-6.00   sec  0.00 Bytes  0.00 bits/sec
  [  5]   6.00-7.00   sec  0.00 Bytes  0.00 bits/sec
  [  5]   7.00-8.00   sec  0.00 Bytes  0.00 bits/sec

When this infinitely repeating "0.00 bits/sec" problem is encountered,
the server is restarted.

Note that when being run on Windows, this script needs to be used in conjunction
with a patched iperf binary.  The important source code change is adding a
stdout flush after printing output::

  diff -urBN iperf-3.0.10/src/iperf_api.c iperf-3.0.10-patch/src/iperf_api.c
  --- iperf-3.0.10/src/iperf_api.c      2014-12-16 11:39:58.000000000 -0800
  +++ iperf-3.0.10-patch/src/iperf_api.c        2014-12-19 21:26:27.108536953
  -0800
  @@ -2668,5 +2668,6 @@
            TAILQ_INSERT_TAIL(&(test->server_output_list), l, textlineentries);
        }
       }
  +    fflush(stdout);
       return r;
   }

Currently, all files necessary to run iperf on Windows are contained within
these two archives, which are not source-controlled::

- iperf3-3.0.10-win32_server-src.tar.gz
- iperf3-3.0.10-win32_server-bin.tar.gz
"""


from __future__ import print_function

import subprocess
import sys


IPERF_ERROR_IN_USE = ('error - unable to start listener for connections: '
                      'Address already in use')
IPERF_ZERO_SPEED_STR = '0.00 bits/sec'


def RunIperf3Server():
  # Assume on non-Windows platforms:
  # (1) iperf3 has not been patched with added stdout flushing.
  # (2) GNU coreutils stdbuf is available to force unbuffered output.
  iperf_cmd = ['iperf3', '-s']
  if sys.platform != 'win32':
    iperf_cmd = ['stdbuf', '-oL'] + iperf_cmd

  while True:
    print('::: starting new iperf3 process')
    proc = subprocess.Popen(
        iperf_cmd,
        bufsize=0,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)

    fail_count = 0
    for line in iter(proc.stdout.readline, b''):
      line = line.rstrip()

      print(line)
      if IPERF_ERROR_IN_USE in line:
        print('::: aborting since another process is already running')
        proc.terminate()
        return

      if IPERF_ZERO_SPEED_STR in line:
        fail_count += 1
      else:
        fail_count = 0

      if fail_count == 5:
        print('::: terminated due to 0.00 bits/sec')
        proc.terminate()
        break


if __name__ == '__main__':
  RunIperf3Server()
