# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Factory Update Server.

The factory update server is implemented as a thread to be started by
shop floor server.  It monitors the given state_dir and detects
factory.tar.bz2 file changes and then sets up the new update files
into factory_dir (under state_dir).  It also starts an rsync server
to serve factory_dir for clients to fetch update files.
'''

import glob
import logging
import os
import shutil
import subprocess
import threading

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


FACTORY_DIR = 'factory'
AUTOTEST_DIR = 'autotest'
TARBALL_NAME = 'factory.tar.bz2'
LATEST_SYMLINK = 'latest'
LATEST_MD5SUM = 'latest.md5sum'
MD5SUM = 'MD5SUM'
DEFAULT_RSYNCD_PORT = 8083
RSYNCD_CONFIG_TEMPLATE = '''port = %(port)d
pid file = %(pidfile)s
log file = %(logfile)s
use chroot = no
[factory]
  path = %(factory_dir)s
  read only = yes
'''


def StartRsyncServer(port, state_dir, factory_dir):
  configfile = os.path.join(state_dir, 'rsyncd.conf')
  pidfile = os.path.join(state_dir, 'rsyncd.pid')
  if os.path.exists(pidfile):
    # Since rsyncd will not overwrite it if it already exists
    os.unlink(pidfile)
  logfile = os.path.join(state_dir, 'rsyncd.log')
  data = RSYNCD_CONFIG_TEMPLATE % dict(port=port,
                                       pidfile=pidfile,
                                       logfile=logfile,
                                       factory_dir=factory_dir)
  with open(configfile, 'w') as f:
    f.write(data)

  p = Spawn(['rsync', '--daemon', '--no-detach', '--config=%s' % configfile],
            log=True)
  logging.info('Rsync server (pid %d) started on port %d', p.pid, port)
  return p


def StopRsyncServer(rsyncd_process):
  logging.info('Stopping rsync server (pid %d)', rsyncd_process.pid)
  TerminateOrKillProcess(rsyncd_process)
  logging.debug('Rsync server stopped')


def CalculateMd5sum(filename):
  p = subprocess.Popen(('md5sum', filename), stdout=subprocess.PIPE)
  output, _ = p.communicate()
  return output.split()[0]


class ChangeDetector(object):
  """Detects changes in a file.

  Properties:
    path: The last path detected to the file.
  """
  def __init__(self, pattern):
    """Constructor:

    Args:
      pattern: The path (or pattern) to monitor.
    """
    self.pattern = pattern
    self.path = None
    self.stat = None

  def HasChanged(self):
    """Returns True if the file has changed since the last invocation."""
    paths = glob.glob(self.pattern)

    last_path = self.path
    last_stat = self.stat

    if len(paths) != 1:
      if not paths:
        # No files; that's OK
        pass
      else:
        # Multiple files; that's a problem!
        logging.warn('Multiple files match pattern %s', self.pattern)

      self.path = None
      self.stat = None
      return self.path != last_path

    self.path = paths[0]
    self.stat = os.stat(self.path)

    return (self.path != last_path or
            not last_stat or
            ((self.stat.st_mtime, self.stat.st_size) !=
             (last_stat.st_mtime, last_stat.st_size)))


class FactoryUpdateServer():
  poll_interval_sec = 1

  def __init__(self, state_dir, rsyncd_port=DEFAULT_RSYNCD_PORT, on_idle=None):
    """Constructor.

    Args:
      state_dir: Update state directory (generally shopfloor_data/update).
      rsyncd_port: Port on which to open rsyncd.
      on_idle: If non-None, a function to call on idle (generally every
        second).
    """
    self.state_dir = state_dir
    self.factory_dir = os.path.join(state_dir, FACTORY_DIR)
    self.rsyncd_port = rsyncd_port
    if not os.path.exists(self.factory_dir):
      os.mkdir(self.factory_dir)
    self.hwid_path = None
    self.on_idle = on_idle

    self._stop_event = threading.Event()
    self._rsyncd = StartRsyncServer(rsyncd_port, state_dir, self.factory_dir)
    self._tarball_path = os.path.join(self.state_dir, TARBALL_NAME)

    self._thread = None
    self._run_count = 0
    self._update_count = 0
    self._errors = 0

    self._factory_detector = ChangeDetector(self._tarball_path)
    self._hwid_detector = ChangeDetector(
        os.path.join(state_dir, 'hwid_*.sh'))

  def Start(self):
    assert not self._thread
    self._thread = threading.Thread(target=self.Run)
    self._thread.start()

  def Stop(self):
    if self._rsyncd:
      StopRsyncServer(self._rsyncd)
      self._rsyncd = None

    self._stop_event.set()

    if self._thread:
      self._thread.join()
      self._thread = None

  def GetTestMd5sum(self):
    """Returns the MD5SUM of the current update tarball."""
    if not self._factory_detector.path:
      return None

    md5file = os.path.join(self.state_dir, FACTORY_DIR, LATEST_MD5SUM)
    if not os.path.isfile(md5file):
      return None
    with open(md5file, 'r') as f:
      return f.readline().strip()

  def _HandleTarball(self):
    new_tarball_path = self._tarball_path + '.new'

    # Copy the tarball to avoid possible race condition.
    shutil.copyfile(self._tarball_path, new_tarball_path)

    # Calculate MD5.
    md5sum = CalculateMd5sum(new_tarball_path)
    logging.info('Processing tarball ' + self._tarball_path + ' (md5sum=%s)',
                 md5sum)

    # Move to a file containing the MD5.
    final_tarball_path = self._tarball_path + '.' + md5sum
    os.rename(new_tarball_path, final_tarball_path)

    # Create subfolder to hold tarball contents.
    final_subfolder = os.path.join(self.factory_dir, md5sum)
    final_md5sum = os.path.join(final_subfolder, FACTORY_DIR, MD5SUM)
    if os.path.exists(final_subfolder):
      if not (os.path.exists(final_md5sum) and
              open(final_md5sum).read().strip() == md5sum):
        logging.warn('Update directory %s appears not to be set up properly '
                     '(missing or bad MD5SUM); delete it and restart update '
                     'server?', final_subfolder)
        return
      logging.info('Update is already deployed into %s', final_subfolder)
    else:
      new_subfolder = final_subfolder + '.new'
      if os.path.exists(new_subfolder):
        shutil.rmtree(new_subfolder)
      os.mkdir(new_subfolder)

      # Extract tarball.
      success = False
      try:
        try:
          logging.info('Staging into %s', new_subfolder)
          subprocess.check_call(('tar', '-xjf', final_tarball_path,
                                 '-C', new_subfolder))
        except subprocess.CalledProcessError:
          logging.error('Failed to extract update files to subfolder %s',
                        new_subfolder)
          return

        missing_dirs = [
          d for d in (FACTORY_DIR, AUTOTEST_DIR)
          if not os.path.exists(os.path.join(new_subfolder, d))]
        if missing_dirs:
          logging.error('Tarball is missing directories: %r', missing_dirs)
          return

        factory_dir = os.path.join(new_subfolder, FACTORY_DIR)
        with open(os.path.join(factory_dir, MD5SUM), 'w') as f:
          f.write(md5sum)

        # Extracted and verified.  Move it in place.
        os.rename(new_subfolder, final_subfolder)
        logging.info('Moved to final directory %s', final_subfolder)

        success = True
        self._update_count += 1
      finally:
        if os.path.exists(new_subfolder):
          shutil.rmtree(new_subfolder, ignore_errors=True)
        if (not success) and os.path.exists(final_subfolder):
          shutil.rmtree(final_subfolder, ignore_errors=True)

    # Update symlink and latest.md5sum.
    linkname = os.path.join(self.factory_dir, LATEST_SYMLINK)
    if os.path.islink(linkname):
      os.remove(linkname)
    os.symlink(md5sum, linkname)
    with open(os.path.join(self.factory_dir, LATEST_MD5SUM), 'w') as f:
      f.write(md5sum)
    logging.info('Update files (%s) setup complete', md5sum)

  def Run(self):
    while True:
      try:
        self.RunOnce()
      except:  # pylint: disable=W0702
        logging.exception('Error in event loop')

      self._stop_event.wait(self.poll_interval_sec)
      if self._stop_event.is_set():
        break

  def RunOnce(self):
    try:
      self._run_count += 1

      if self._factory_detector.HasChanged():
        if self._factory_detector.path:
          logging.info('Verifying integrity of tarball %s',
                       self._factory_detector.path)
          process = Spawn(['tar', '-tjf', self._tarball_path],
                          ignore_stdout=True, ignore_stderr=True, call=True)
          if process.returncode == 0:
            # Re-stat in case it finished being written while we were
            # verifying it.
            self._factory_detector.HasChanged()
            self._HandleTarball()
          else:
            logging.warn(
                'Tarball %s (%d bytes) is corrupt or incomplete',
                self._tarball_path, os.path.getsize(self._tarball_path))
        else:
          # It's disappeared!
          logging.warn('Tarball %s has disappeared',
                       self._tarball_path)

      if self._hwid_detector.HasChanged():
        self.hwid_path = self._hwid_detector.path
        if self.hwid_path is None:
          logging.warn('HWID bundle %s is no longer valid',
                       self._hwid_detector.pattern)
        else:
          logging.info('Found new HWID bundle %s (MD5SUM %s); serving it',
                       self.hwid_path, CalculateMd5sum(self.hwid_path))

      if self.on_idle:
        try:
          self.on_idle()
        except:  # pylint: disable=W0702
          logging.exception('Exception in idle hook')
    except:
      self._errors += 1
      raise
