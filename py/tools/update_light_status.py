#!/usr/bin/python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a tool for Overlord fixtures, the script will keep updating light
status by sending corresponding commands. The commands are read from a
configuration file, default is "/usr/local/factory/properties.json". The
configuration file should specify a list of commands to execute and the polling
interval for each command.
"""

import argparse
import json
import subprocess
import sys
import time
from Queue import PriorityQueue


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '-c',
      '--config',
      default='/usr/local/factory/properties.json',
      help=('Specify path to the config file, '
            'default file: /usr/local/factory/properties.json'))

  args = parser.parse_args()

  with open(args.config) as f:
    properties = json.load(f)
    try:
      lights = properties['ui']['lights']['items']
    except Exception:
      print "[ERROR] Can't find ui > lights > items entry in ``%s''" % args.config
      sys.exit(0)

    queue = PriorityQueue(len(lights))

    for light in lights:
      if 'poll' in light:
        poll = light['poll']
        poll['interval'] = max(poll.get('interval', 0), 10000)
        queue.put((time.time(), poll))
      if 'init_cmd' in light:
        subprocess.call(light['init_cmd'], shell=True)

    if queue.empty():
      sys.exit(0)

    try:
      while True:
        (when, poll) = queue.get_nowait()
        if time.time() < when: # not now
          queue.put((when, poll))
          time.sleep(when - time.time())
        else:
          subprocess.call(poll['cmd'], shell=True)
          queue.put((time.time() + (poll['interval'] / 1000.0), poll))
    except (KeyboardInterrupt, SystemExit):
      pass


if __name__ == '__main__':
  main()
