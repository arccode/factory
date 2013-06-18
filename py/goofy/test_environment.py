#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cPickle as pickle
import datetime
import glob
import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.test import factory
from cros.factory.goofy import connection_manager
from cros.factory.test import state
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


class Environment(object):
  '''
  Abstract base class for external test operations, e.g., run an autotest,
  shutdown, or reboot.

  The Environment is assumed not to be thread-safe: callers must grab the lock
  before calling any methods.  This is primarily necessary because we mock out
  this Environment with mox, and unfortunately mox is not thread-safe.
  TODO(jsalz): Try to write a thread-safe wrapper for mox.
  '''
  lock = threading.Lock()

  def shutdown(self, operation):
    '''
    Shuts the machine down (from a ShutdownStep).

    Args:
      operation: 'reboot' or 'halt'.

    Returns:
      True if Goofy should gracefully exit, or False if Goofy
        should just consider the shutdown to have suceeded (e.g.,
        in the chroot).
    '''
    raise NotImplementedError()

  def launch_chrome(self):
    '''
    Launches Chrome.

    Returns:
      The Chrome subprocess (or None if none).
    '''
    raise NotImplementedError()

  def spawn_autotest(self, name, args, env_additions, result_file):
    '''
    Spawns a process to run an autotest.

    Args:
      name: Name of the autotest to spawn.
      args: Command-line arguments.
      env_additions: Additions to the environment.
      result_file: Expected location of the result file.
    '''
    raise NotImplementedError()

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    '''
    Creates a ConnectionManager.
    '''
    raise NotImplementedError()


class DUTEnvironment(Environment):
  '''
  A real environment on a device under test.
  '''
  def shutdown(self, operation):
    assert operation in ['reboot', 'halt']
    logging.info('Shutting down: %s', operation)
    subprocess.check_call('sync')
    subprocess.check_call(operation)
    time.sleep(30)
    assert False, 'Never reached (should %s)' % operation

  def spawn_autotest(self, name, args, env_additions, result_file):
    return self.goofy.prespawner.spawn(args, env_additions)

  def launch_chrome(self):
    # The cursor speed needs to be adjusted when running in QEMU
    # (but after Chrome starts and has fiddled with the settings
    # itself).
    if utils.in_qemu():
      def FixCursor():
        for _ in xrange(6):  # Every 500ms for 3 seconds
          time.sleep(.5)
          subprocess.check_call(['xset','m','200','200'])

      thread = threading.Thread(target=FixCursor)
      thread.daemon = True
      thread.start()

    chrome_data_dir = os.path.join(factory.get_state_root(),
                                   'chrome-data-dir')
    # Start with a fresh data directory every time.
    shutil.rmtree(chrome_data_dir, ignore_errors=True)

    # Setup GPU & acceleration flags which differ between x86/ARM SoC
    system_info = system.SystemInfo()
    if system_info.architecture == "armv7l":
      accelerated_flag = "--use-gl=egl"
      vda_flag='--use-exynos-vda'
    else:
      accelerated_flag = "--enable-accelerated-layers"
      vda_flag=''

    # Auto detect the display modes on DUT
    mode_paths = glob.glob('/sys/class/drm/card*/modes')
    available_modes = []
    for path in mode_paths:
      with open(path, 'r') as fd:
        available_modes.extend(
          line.strip().split('x') for line in open(path).readlines())
    if not available_modes:
      raise factory.FactoryTestFailure('No display mode was found')
    logging.info('Supported display modes: %s', available_modes)
    screen_width, screen_height = [int(x) for x in available_modes[0]]
    if self.goofy.options.one_pixel_less:
      screen_width -= 1

    chrome_command = [
      '/opt/google/chrome/chrome',
      '--ash-host-window-bounds=%dx%d' % (screen_width, screen_height),
      '--ash-hide-notifications-for-factory',
      '--user-data-dir=%s' % chrome_data_dir,
      '--disable-translate',
      '--aura-host-window-use-fullscreen',
      '--kiosk',
      '--kiosk-mode-screensaver-path=/dev/null',
      '--use-cras',
      '--enable-audio-mixer',
      '--enable-renderer-side-mixing',
      accelerated_flag,
      vda_flag,
      ('--default-device-scale-factor=%d' %
       self.goofy.options.ui_scale_factor),
      '--disable-extensions',
      # Hard-code localhost IP so Chrome doesn't have to rely on DNS.
      'http://127.0.0.1:%d/' % state.DEFAULT_FACTORY_STATE_PORT,
      ]

    if self.goofy.options.automation:
      # Automation script will be responsible for opening chrome browser
      # argument order:
      # chrome_binary_location, option1, option2, ..., factory_url
      automation_command = [
          '/usr/local/factory/py/automation/factory_automation.py']
      automation_command.extend(chrome_command)

      automation_log = os.path.join(factory.get_log_root(),
                                    'factory_automation.log')
      automation_log_file = open(automation_log, 'a')

      # Make sure chromedriver is in the system path
      new_env = os.environ.copy()
      new_env['PATH'] += ':/usr/local/factory/bin'

      logging.info('Launching factory_automation: log in %s', automation_log)
      process = Spawn(automation_command,
                      stdout=automation_log_file,
                      stderr=subprocess.STDOUT,
                      # Make other automation logs go to the correct place
                      cwd=factory.get_log_root(),
                      env=new_env)
    else:
      chrome_log = os.path.join(factory.get_log_root(), 'factory.chrome.log')
      chrome_log_file = open(chrome_log, 'a', 0)
      chrome_log_file.write('#\n# %s: Starting chrome\n#\n' %
                            datetime.datetime.now().isoformat())
      logging.info('Launching Chrome; logs in %s', chrome_log)
      process = Spawn(chrome_command,
                      stdout=chrome_log_file,
                      stderr=subprocess.STDOUT,
                      log=True)

    logging.info('Chrome has been launched: PID %d', process.pid)
    # Start thread to wait for Chrome to die and log its return
    # status
    def WaitForChrome():
      returncode = process.wait()
      logging.info('Chrome exited with return code %d', returncode)
      chrome_log_file.write('#\n# %s: Chrome exited with return code %d\n#\n' %
                            (datetime.datetime.now().isoformat(), returncode))
    utils.StartDaemonThread(target=WaitForChrome)

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.ConnectionManager(wlans,
                                                scan_wifi_period_secs)


class FakeChrootEnvironment(Environment):
  '''
  A chroot environment that doesn't actually shutdown or run autotests.
  '''
  def shutdown(self, operation):
    assert operation in ['reboot', 'halt']
    logging.warn('In chroot: skipping %s', operation)
    return False

  def spawn_autotest(self, name, args, env_additions, result_file):
    logging.warn('In chroot: skipping autotest %s', name)
    # Mark it as passed with 75% probability, or failed with 25%
    # probability (depending on a hash of the autotest name).
    pseudo_random = ord(hashlib.sha1(name).digest()[0]) / 256.0
    passed = pseudo_random > .25

    with open(result_file, 'w') as out:
      pickle.dump((passed, '' if passed else 'Simulated failure'), out)
    # Start a process that will return with a true exit status in
    # 2 seconds (just like a happy autotest).
    return subprocess.Popen(['sleep', '2'])

  def launch_chrome(self):
    logging.warn('In chroot; not launching Chrome. '
           'Please open http://localhost:%d/ in Chrome.',
           state.DEFAULT_FACTORY_STATE_PORT)

  def create_connection_manager(self, wlans, scan_wifi_period_secs):
    return connection_manager.DummyConnectionManager()
