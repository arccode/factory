#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import re
import sys
import yaml
from collections import defaultdict

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils.process_utils import Spawn


DESCRIPTION = """Scans existing HWID databases files for matching components.

All boards in chromeos-hwid/boards.yaml are scanned, on the corresponding branch
listed in that file.
"""


def main():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('probe_results', metavar='FILE.yaml',
                      help=('A file containing YAML-formatted probe results '
                            'output by "gooftool probe".'))
  parser.add_argument('--board', '-b', metavar='B',
                      action='append', dest='boards',
                      help=('Board to scan (may be provided multiple times, '
                            'e.g., "--board A --board B").  If no --board '
                            'argument is provided, all known boards are '
                            'scanned.'))
  args = parser.parse_args()

  SetupLogging(level=logging.INFO)

  hwid_dir = os.path.dirname(common.DEFAULT_HWID_DATA_PATH)
  boards_yaml_path = os.path.join(hwid_dir, 'boards.yaml')
  with open(boards_yaml_path) as f:
    boards_yaml = yaml.load(f)

  board_dbs = {}

  if args.boards:
    args.boards = [x.upper() for x in args.boards]
    missing_boards = set(args.boards) - set(boards_yaml.keys())
    if missing_boards:
      print sys.stderr, 'Unknown board(s) %r; valid choices are %r' % (
          missing_boards, sorted(boards_yaml.keys()))

  for board, board_info in sorted(boards_yaml.items()):
    if board_info['version'] != 3:
      continue
    if args.boards and board not in args.boards:
      continue
    logging.info('Reading %(path)s on branch %(branch)s', board_info)
    board_db_yaml = Spawn(
        ['git', 'show', 'cros-internal/%(branch)s:%(path)s' % board_info],
        check_output=True, log_stderr_on_error=True, cwd=hwid_dir).stdout_data

    board_dbs[board] = database.Database.LoadData(yaml.load(board_db_yaml),
                                                  strict=False)

  with open(args.probe_results) as f:
    probe_result = f.read()

  # Map from (board, component_class) to the matching probe result.
  matches = defaultdict(list)
  # Map from board -> list of matching results.
  board_matches = defaultdict(list)
  # Map from component -> list of matching results.
  component_matches = defaultdict(list)

  # Loop through each board and see what the probe result matches, if anything.
  boms = {}
  for board, board_db in sorted(board_dbs.items()):
    bom = board_db.ProbeResultToBOM(probe_result)
    boms[board] = bom
    for component_class, results in sorted(bom.components.items()):
      if component_class in ['hash_gbb', 'key_recovery', 'key_root',
                             'ro_main_firmware', 'rw_main_firmware',
                             'ro_ec_firmware', 'rw_ec_firmware']:
        # We don't really care for these pseudo-components
        continue
      for result in results:
        if result.error:
          # Not a match at all
          continue
        if result.component_name == 'opaque':
          # Not a true match
          continue
        matches[board, component_class].append(result)
        board_matches[board].append((component_class, result))
        component_matches[component_class].append((board, result))

  separator = '\n' + ('-' * 40)

  # Summarize to board and component view.
  print separator
  print 'Matches by board:'
  for board, results in sorted(board_matches.items()):
    print '  %s matches:' % board
    for component_class, r in results:
      print '    %s: %s' % (component_class, r.component_name)

  print separator
  print 'Matches by component class:'
  for component_class, results in sorted(component_matches.items()):
    print '  %s matches:' % component_class
    for board, r in results:
      print '    %s: %s' % (board, r.component_name)

  # Detailed view.
  print separator
  print 'Detailed information about matches:'
  yaml_out = {}
  for k, results in sorted(matches.items()):
    board, component_class = k
    items = {}
    yaml_out['%s %s' % (board, component_class)] = items
    for r in results:
      items[r.component_name] = r.probed_values

  out = yaml.dump(yaml_out)
  # Indent by 2 spaces
  out = re.sub('(?m)^', '  ', out)
  print out

if __name__ == '__main__':
  main()
