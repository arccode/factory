#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.test.dut.link.DUTLink using ADB."""

import logging
import os
import pipes
import subprocess
import tempfile
import uuid

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import link
from cros.factory.utils import file_utils


class ADBProcess(object):

  def __init__(self, proxy_object, session_id):
    self._proxy_object = proxy_object
    self._session_id = session_id
    self._exit_code = None

  def __getattr__(self, name):
    if name == 'returncode':
      return self._get_dut_returncode()
    return getattr(self._proxy_object, name)

  def _get_dut_returncode(self):
    # The returncode will only be 0 if ADB channel was created and then closed
    # successfully, not the real status of remote process.
    if self._proxy_object.returncode is not 0:
      return self._proxy_object.returncode

    # Use cached exit code if possible.
    if self._exit_code is not None:
      return self._exit_code

    # To get real exit code, we want to find out using logcat (see
    # implementation in ADBLink).
    result = subprocess.check_output('adb logcat -d -b main -s %s' %
                                     self._session_id, shell=True).strip()
    logging.debug('%s: Exit Results = %s', type(self), result)

    # Format: I/session_id(PID): EXITCODE
    # Example: I/64eeb606-fdcf-11e4-b63f-80c16efb89a5( 3439): 0
    self._exit_code = int(result.rpartition(':')[2].strip())
    return self._exit_code


class ADBLink(link.DUTLink):
  """A DUT target that is connected via ADB interface."""

  def __init__(self, temp_dir='/data/local/tmp'):
    self._temp_dir = temp_dir

  def Push(self, local, remote):
    """See DUTLink.Push"""
    subprocess.check_output(['adb', 'push', local, remote],
                            stderr=subprocess.STDOUT)

  def Pull(self, remote, local=None):
    """See DUTLink.Pull"""
    if local is None:
      with file_utils.UnopenedTemporaryFile() as path:
        self.Pull(remote, path)
        with open(path) as f:
          return f.read()

    subprocess.check_output(['adb', 'pull', remote, local],
                            stderr=subprocess.STDOUT)

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """See DUTLink.Shell"""
    # ADB shell has a bug that exit code is not correctly returned (
    #  https://code.google.com/p/android/issues/detail?id=3254 ). Many public
    # implementations work around that by adding an echo and then parsing the
    # execution results. To avoid problems in redirection, we do this slightly
    # different by using the log service and "logcat" ADB feature.

    # ADB shell does not provide interactive shell, which means we are not
    # able to send stdin data in an interactive way (
    # https://code.google.com/p/android/issues/detail?id=74856). As described
    # in the issue, this and the above exit code bugs will be fixed in the
    # future build. Now we use a temp file and print warning message when use
    # PIPE to avoid unexpected bug.

    session_id = str(uuid.uuid1())

    # Convert list-style commands to single string because we need to run
    # multiple commands in same session (and needs shell=True).
    if not isinstance(command, basestring):
      command = ' '.join(pipes.quote(param) for param in command)

    # ADB protocol currently mixes stderr and stdout in same channel (i.e., the
    # stdout by adb command has both stderr and stdout from DUT) so we do want
    # to make them different.
    redirections = ''
    if stderr is None:
      redirections += '2>/dev/null'
    elif stderr == subprocess.STDOUT:
      pass  # No need to redirect because that's the default behavior.
    else:
      # TODO(hungte) Create a temp file remotely and store contents there, or
      # figure out a way to return by logcat.
      redirections += '2>/dev/null'
      logging.warn('%s: stderr redirection is not supported yet.',
                   type(self).__name__)

    delete_tmps = ''
    if stdin is not None:
      if stdin == subprocess.PIPE:
        logging.warn('%s: stdin PIPE is not supported yet.',
                     type(self).__name__)
      else:
        with tempfile.NamedTemporaryFile() as tmp_file:
          data = stdin.read()
          tmp_file.write(data)
          tmp_file.flush()

          filename = os.path.basename(tmp_file.name)

          # We don't know the correct way to create true tmp file on the DUT
          # since it differs from board to board. Use session_id in the
          # filename to avoid collision as much as possible.
          target_tmp_file = os.path.join(
              self._temp_dir, '%s.%s' % (session_id, filename))

          self.Push(tmp_file.name, target_tmp_file)
          redirections += ' <%s' % target_tmp_file
          delete_tmps = 'rm -f %s' % target_tmp_file

    command = ['adb', 'shell', '( %s ) %s; log -t %s $?; %s' %
               (command, redirections, session_id, delete_tmps)]
    logging.debug('ADBLink: Run %r', command)
    return ADBProcess(subprocess.Popen(command, shell=False, close_fds=True,
                                       stdin=stdin, stdout=stdout,
                                       stderr=stderr), session_id)

  def IsReady(self):
    """See DUTLink.IsReady"""
    return subprocess.check_output(['adb', 'get-state']).strip() == 'device'
