#!/usr/bin/python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
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

All projects in chromeos-hwid/projects.yaml are scanned, on the corresponding
branch listed in that file.
"""


def _DetectUnknownChoices(choice_name, choices, valid_choices):
  unknown_choices = set(choices) - set(valid_choices)
  if unknown_choices:
    print sys.stderr, 'Unknown %s(s) %r; valid choices are %r' % (
        choice_name, unknown_choices, sorted(valid_choices))


def main():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('probe_results', metavar='FILE.yaml',
                      help=('A file containing YAML-formatted probe results '
                            'output by "gooftool probe".'))
  parser.add_argument('--board', '-b', metavar='BOARD',
                      action='append', dest='boards',
                      help=('Board to scan (may be provided multiple times, '
                            'e.g., "--board A --board B").'))
  parser.add_argument('--project', '-p', metavar='PROJECT',
                      action='append', dest='projects',
                      help=('Project to scan (may be provided multiple times, '
                            'e.g., "--project A --project B").  If neither '
                            '--project nor --board arguments are provided, all '
                            'known projects are scanned.'))
  args = parser.parse_args()
  args.projects = args.projects or []
  args.boards = args.boards or []

  SetupLogging(level=logging.INFO)

  hwid_dir = os.path.dirname(common.DEFAULT_HWID_DATA_PATH)
  projects_yaml_path = os.path.join(hwid_dir, 'projects.yaml')
  with open(projects_yaml_path) as f:
    projects_yaml = yaml.load(f)

  project_dbs = {}

  if args.projects:
    args.projects = [x.upper() for x in args.projects]
    _DetectUnknownChoices('project', args.projects, projects_yaml.keys())

  if args.boards:
    args.boards = [x.upper() for x in args.boards]
    _DetectUnknownChoices('board', args.boards,
                          [v['board'] for v in projects_yaml.itervalues()])

  only_scan_user_specific = args.projects or args.boards

  for project, project_info in sorted(projects_yaml.items()):
    if project_info['version'] != 3:
      continue
    if (only_scan_user_specific and
        project not in args.projects and
        project_info['board'] not in args.boards):
      continue
    logging.info('Reading %(path)s on branch %(branch)s', project_info)
    project_db_yaml = Spawn(
        ['git', 'show', 'cros-internal/%(branch)s:%(path)s' % project_info],
        check_output=True, log_stderr_on_error=True, cwd=hwid_dir).stdout_data

    project_dbs[project] = database.Database.LoadData(
        yaml.load(project_db_yaml), strict=False)

  with open(args.probe_results) as f:
    probe_result = f.read()

  # Map from (project, component_class) to the matching probe result.
  matches = defaultdict(list)
  # Map from project -> list of matching results.
  project_matches = defaultdict(list)
  # Map from component -> list of matching results.
  component_matches = defaultdict(list)

  # Loop through each project and see what the probe result matches, if
  # anything.
  boms = {}
  for project, project_db in sorted(project_dbs.items()):
    bom = project_db.ProbeResultToBOM(probe_result)
    boms[project] = bom
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
        matches[project, component_class].append(result)
        project_matches[project].append((component_class, result))
        component_matches[component_class].append((project, result))

  separator = '\n' + ('-' * 40)

  # Summarize to project and component view.
  print separator
  print 'Matches by project:'
  for project, results in sorted(project_matches.items()):
    print '  %s matches:' % project
    for component_class, r in results:
      print '    %s: %s' % (component_class, r.component_name)

  print separator
  print 'Matches by component class:'
  for component_class, results in sorted(component_matches.items()):
    print '  %s matches:' % component_class
    for project, r in results:
      print '    %s: %s' % (project, r.component_name)

  # Detailed view.
  print separator
  print 'Detailed information about matches:'
  yaml_out = {}
  for k, results in sorted(matches.items()):
    project, component_class = k
    items = {}
    yaml_out['%s %s' % (project, component_class)] = items
    for r in results:
      items[r.component_name] = r.probed_values

  out = yaml.dump(yaml_out)
  # Indent by 2 spaces
  out = re.sub('(?m)^', '  ', out)
  print out

if __name__ == '__main__':
  main()
