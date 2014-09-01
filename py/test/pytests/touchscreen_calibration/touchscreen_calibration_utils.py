# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common utility functions that are not touch specific.

The SimpleSystem() and SimpleSystemOutput() functions are grabbed from
hardware_Trackpad and were written by truty@.

Note that in order to be able to use this module on a system without the
factory stuffs, e.g., on a Beagle Bone, this module does not depend on
any factory modules on purpose.
"""

from __future__ import print_function

import logging
import re
import subprocess

from subprocess import PIPE, STDOUT


class Error(Exception):
  pass


def SimpleSystem(cmd):
  """Execute a system command."""
  ret = subprocess.call(cmd, shell=True)
  if ret:
    logging.warning('Command (%s) failed (ret=%s).', cmd, ret)
  return ret


def SimpleSystemOutput(cmd):
  """Execute a system command and get its output."""
  try:
    proc = subprocess.Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
    stdout, _ = proc.communicate()
  except Exception, e:
    logging.warning('Command (%s) failed (%s).', cmd, e)
  else:
    return None if proc.returncode else stdout.strip()


def IsDestinationPortEnabled(port):
  """Check if the destination port is enabled.

  If port 8000 is enabled, it looks like
    ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  ctstate NEW tcp dpt:8000
  """
  pattern = re.compile('ACCEPT\s+tcp\s+0.0.0.0/0\s+0.0.0.0/0\s+ctstate\s+'
                       'NEW\s+tcp\s+dpt:%d' % port)
  rules = SimpleSystemOutput('iptables -L INPUT -n --line-number')
  for rule in rules.splitlines():
    if pattern.search(rule):
      return True
  return False


def EnableDestinationPort(port):
  """Eanble the destination port in iptables."""
  cmd = ('iptables -A INPUT -p tcp -m conntrack --ctstate NEW --dport %d '
         '-j ACCEPT' % port)
  if SimpleSystem(cmd) != 0:
    raise Error('Failed to enable destination port in iptables: %d.' % port)
