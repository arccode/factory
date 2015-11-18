#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import logging
from subprocess import Popen, PIPE

import factory_common  # pylint: disable=W0611
from cros.factory.utils.type_utils import Obj


# TODO(hungte) Deprecate this by dut.Shell
def Shell(cmd, stdin=None, log=True):
  """Run cmd in a shell, return Obj containing stdout, stderr, and status.

  The cmd stdout and stderr output is debug-logged.

  Args:
    cmd: Full shell command line as a string, which can contain
      redirection (popes, etc).
    stdin: String that will be passed as stdin to the command.
    log: log command and result.
  """
  process = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
  stdout, stderr = process.communicate(input=stdin)  # pylint: disable=E1123
  if log:
    logging.debug('running %s' % repr(cmd) +
                  (', stdout: %s' % repr(stdout.strip()) if stdout else '') +
                  (', stderr: %s' % repr(stderr.strip()) if stderr else ''))
  status = process.poll()
  return Obj(stdout=stdout, stderr=stderr, status=status, success=(status == 0))
