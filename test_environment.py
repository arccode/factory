#!/usr/bin/python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cPickle as pickle
import hashlib
import logging
import os
from Queue import Queue
import re
import subprocess
import threading
import time

import factory_common
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import shopfloor
from autotest_lib.client.cros.factory import state
from autotest_lib.client.cros.factory import updater


ECTOOL_TIMEOUT_SEC = 0.1


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
        chrome_command = [
            '/opt/google/chrome/chrome',
            '--user-data-dir=%s/factory-chrome-datadir' %
            factory.get_log_root(),
            '--aura-host-window-use-fullscreen',
            '--kiosk',
            ('--default-device-scale-factor=%d' %
             self.goofy.options.ui_scale_factor),
            'http://localhost:%d/' % state.DEFAULT_FACTORY_STATE_PORT,
            ]

        chrome_log = os.path.join(factory.get_log_root(), 'factory.chrome.log')
        chrome_log_file = open(chrome_log, "a")
        logging.info('Launching Chrome; logs in %s' % chrome_log)
        return subprocess.Popen(chrome_command,
                                stdout=chrome_log_file,
                                stderr=subprocess.STDOUT)


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


class SystemInfo(object):
    '''Information about the system.'''
    def __init__(self, env, state):
        self.serial_number = None
        try:
            self.serial_number = shopfloor.get_serial_number()
        except:
            pass

        self.factory_image_version = None
        try:
            lsb_release = open('/etc/lsb-release').read()
            match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release,
                              re.MULTILINE)
            if match:
                self.factory_image_version = match.group(1)
        except:
            pass

        try:
            self.wlan0_mac = open('/sys/class/net/wlan0/address').read().strip()
        except:
            self.wlan0_mac = None

        try:
            uname = subprocess.Popen(['uname', '-r'], stdout=subprocess.PIPE)
            stdout, _ = uname.communicate()
            self.kernel_version = stdout.strip()
        except:
            self.kernel_version = None

        self.ec_version = None
        try:
            ectool = subprocess.Popen(['mosys', 'ec', 'info', '-l'],
                                      stdout=subprocess.PIPE)
            stdout, _ = ectool.communicate()
            match = re.search('^fw_version\s+\|\s+(.+)$', stdout,
                              re.MULTILINE)
            if match:
                self.ec_version = match.group(1)
        except:
            pass

        self.firmware_version = None
        try:
            crossystem = subprocess.Popen(['crossystem', 'fwid'],
                                          stdout=subprocess.PIPE)
            stdout, _ = crossystem.communicate()
            self.firmware_version = stdout.strip() or None
        except:
            pass

        self.factory_md5sum = updater.GetCurrentMD5SUM()


if __name__ == '__main__':
    import yaml
    print yaml.dump(SystemInfo(None, None).__dict__,
                    default_flow_style=False)
