#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import array
import fcntl
import glob
import logging
import os
import re
import signal
import subprocess
import time

from autotest_lib.client.cros import factory


def is_process_alive(pid):
    '''
    Returns true if the named process is alive and not a zombie.
    '''
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.readline().split()[2] != 'Z'
    except IOError:
        return False


def kill_process_tree(process, caption):
    '''
    Kills a process and all its subprocesses.

    @param process: The process to kill (opened with the subprocess module).
    @param caption: A caption describing the process.
    '''
    # os.kill does not kill child processes. os.killpg kills all processes
    # sharing same group (and is usually used for killing process tree). But in
    # our case, to preserve PGID for autotest and upstart service, we need to
    # iterate through each level until leaf of the tree.

    def get_all_pids(root):
        ps_output = subprocess.Popen(['ps','--no-headers','-eo','pid,ppid'],
                                     stdout=subprocess.PIPE)
        children = {}
        for line in ps_output.stdout:
            match = re.findall('\d+', line)
            children.setdefault(int(match[1]), []).append(int(match[0]))
        pids = []
        def add_children(pid):
            pids.append(pid)
            map(add_children, children.get(pid, []))
        add_children(root)
        # Reverse the list to first kill children then parents.
        # Note reversed(pids) will return an iterator instead of real list, so
        # we must explicitly call pids.reverse() here.
        pids.reverse()
        return pids

    pids = get_all_pids(process.pid)
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        logging.info('Stopping %s (pid=%s)...', caption, sorted(pids))

        for i in range(25):  # Try 25 times (200 ms between tries)
            for pid in pids:
                try:
                    logging.info("Sending signal %s to %d", sig, pid)
                    os.kill(pid, sig)
                except OSError:
                    pass
            pids = filter(is_process_alive, pids)
            if not pids:
                return
            time.sleep(0.2)  # Sleep 200 ms and try again

    logging.warn('Failed to stop %s process. Ignoring.', caption)


def are_shift_keys_depressed():
    '''Returns True if both shift keys are depressed.'''
    # From #include <linux/input.h>
    KEY_LEFTSHIFT = 42
    KEY_RIGHTSHIFT = 54

    for kbd in glob.glob("/dev/input/by-path/*kbd"):
        try:
            f = os.open(kbd, os.O_RDONLY)
        except OSError as e:
            if factory.in_chroot():
                # That's OK; we're just not root
                continue
            else:
                raise
        buf = array.array('b', [0] * 96)

        # EVIOCGKEY (from #include <linux/input.h>)
        fcntl.ioctl(f, 0x80604518, buf)

        def is_pressed(key):
            return (buf[key / 8] & (1 << (key % 8))) != 0

        if is_pressed(KEY_LEFTSHIFT) and is_pressed(KEY_RIGHTSHIFT):
            return True

    return False


class Enum(frozenset):
    '''An enumeration type.'''
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError
