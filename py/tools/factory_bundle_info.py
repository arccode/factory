#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
from collections import namedtuple
import logging
import os
import re
import subprocess
import sys
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.tools.build_board import BuildBoard
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


BundleFields = ['board', 'base_board', 'created_date', 'factory_toolkit',
                'test_image', 'release_image', 'EC', 'BIOS', 'PD']
BundleInfo = namedtuple('BundleInfo', BundleFields)

DESCRIPTION = """Lists factory bundle information for a board, or
boards with the same base board, or all boards.
Public base board information:
http://www.chromium.org/chromium-os/developer-information-for-chrome-os-devices
"""

EXAMPLES = r"""Examples:
  1. Lists factory bundle info for all boards:
     py/tools/factory_bundle_info.py

  2. Lists factory bundle info for all boards based on rambi:
     py/tools/factory_bundle_info.py --base_board rambi

  3. Lists factory bundle info for squawks:
     py/tools/factory_bundle_info.py --board squawks

  4. Lists factory bundle info for all boards to a HTML file:
     py/tools/factory_bundle_info.py --html_file=bundle.html

  5. Lists factory bundle info using a local boards.yaml file:
     py/tools/factory_bundle_info.py --boards_yaml=boards.yaml
"""


def _GetFactoryBundleInfo(board, factory_branch, repo_sync):
  """Gets factory bundle info from the bundle README file.

  A typical README file has the following format. This function extracts
  Board, Bundle, Factory toolkit, Test image, BIOS and EC info, then returns
  a BundleInfo namedtuple. Some board might have PD firmware.

  ***
  *
  * VITAL INFORMATION
  *
  ***
  Board:                                 squawks
  Bundle:                                20141229_pvt (created by xxxx, ...)
  Factory toolkit:                       5517.274.0
  Test image:                            5978.115.0
  Factory updater MD5SUM:                950b569641e1e4c944c73b3ea39cfe50
  Stateful partition size:               975 MiB (458 MiB free = 46% free)
  Stateful partition inodes:             65536 nodes (46832 free)
  Factory install shim:                  5517.89.0 (mp)
  Release (FSI):                         6310.68.0
  Release (FSI) BIOS:                    Google_Squawks.5216.152.22
  Release (FSI) EC:                      squawks_v1.6.150-0d8dbf2
  firmware/chromeos-firmwareupdate BIOS: Google_Squawks.5216.152.22
  firmware/chromeos-firmwareupdate EC:   squawks_v1.6.150-0d8dbf2
  firmware/chromeos-firmwareupdate PD:   squawks_v1.6.150-0d8dbf2

  ***
  *
  * NOTE
  *
  ***
  This bundle should put image.net.bin into factory image.
  Please use the following commands after you change server ip for
  netboot image.
  ...

  Args:
    board: the board name to get factory bundle info.
    factory_branch: the factory branch of the board.
    repo_sync: whether to 'repo sync' under board private overlays.

  Returns: A BundleInfo tuple.
  """
  overlay_relpath = os.path.join(
      os.environ['CROS_WORKON_SRCROOT'], 'src',
      BuildBoard(board).overlay_relpath)

  bundle_readme_relpath = os.path.join(
      'chromeos-base', 'chromeos-factory-board', 'files', 'bundle', 'README')

  # Do repo sync -n (fetch only, don't update working tree).
  if repo_sync:
    process_utils.Spawn(
        'repo sync -n .',
        log=True, cwd=overlay_relpath, shell=True, check_call=True)

  try:
    bundle_readme = process_utils.CheckOutput(
        ['git', 'show', 'remotes/cros-internal/%s:%s' % (
            factory_branch, bundle_readme_relpath)],
        cwd=overlay_relpath, ignore_stderr=True)
  except subprocess.CalledProcessError:
    logging.warn(
        'Bundle README not found for %s on branch %s', board, factory_branch)
    return None

  # Gets vital info contents.
  vital_info = re.match(
      # Vital info section header
      r'(?:\*\*\*\n\*\n\* VITAL INFORMATION\n\*\n\*\*\*\n)'
      # Anything up to (but not including) the next section header
      r'((?:(?!\*\*\*).)+)', bundle_readme, re.DOTALL)

  # Group(1) contains the 'KEY: VALUE (COMMENT)' pairs in vital contents.
  RE_KEY = r'([\w \(\)\./_-]+)'
  RE_VALUE = r'([\w \._-]+)'
  RE_IGNORE_COMMENT = r'(?: \(.*?\))?'
  RE_VITAL_CONTENTS = RE_KEY + r':\s+' + RE_VALUE + RE_IGNORE_COMMENT + r'\n'
  vital_key_value = re.findall(RE_VITAL_CONTENTS, vital_info.group(1))
  vital_dict = dict((k, v) for k, v in vital_key_value)

  fsi_prefix = 'Release (FSI)'
  fw_updater_prefix = 'firmware/chromeos-firmwareupdate'
  fw_labels = ['BIOS', 'EC', 'PD']
  fw_versions = dict.fromkeys(fw_labels, 'NA')
  for label in fw_labels:
    # The firmware/chromeos-firmwareupdate will be used if it exists.
    # Otherwise, firmware updater extracted from release image will be used.
    for prefix in [fw_updater_prefix, fsi_prefix]:
      if prefix + ' ' + label in vital_dict:
        fw_versions[label] = vital_dict[prefix + ' ' + label]
        break

  # Before toolkit was invented, there is only
  # factory image = toolkit + test image.
  if 'Factory image base' in vital_dict:
    toolkit = test_image = vital_dict['Factory image base']
  else:
    toolkit = vital_dict['Factory toolkit']
    test_image = vital_dict['Test image']

  base_board, _ = _ExtractBaseboardAndVersion(factory_branch)
  return BundleInfo(vital_dict['Board'], base_board,
                    vital_dict['Bundle'], toolkit, test_image,
                    vital_dict[fsi_prefix], fw_versions['EC'],
                    fw_versions['BIOS'], fw_versions['PD'])


def _ExtractBaseboardAndVersion(factory_branch):
  """Extracts base board and main version from a factory branch name.

  By convention, factory branch will be named by 'factory-baseboard-xxxx.B'.
  Some factory might have subversions:
    factory-baseboard-xxxx.xx.B or factory-baseboard-xxxx.xx.xx.B

  Returns: a tuple of (base board, main version) for the factory branch.
      For exmaple, returns ('rambi', 5517) for factory-rambi-5517.12.34.B.
  """
  if factory_branch in _ExtractBaseboardAndVersion.static_dict:
    return _ExtractBaseboardAndVersion.static_dict[factory_branch]

  match = re.match(
      r'factory-(?:([a-z]+)-)?(\d+)(.\d+)?(.\d+)?.B', factory_branch)
  if match is not None:
    _ExtractBaseboardAndVersion.static_dict[factory_branch] = (
        match.group(1), int(match.group(2)))
  else:
    _ExtractBaseboardAndVersion.static_dict[factory_branch] = ('Unknown', 0)
  return _ExtractBaseboardAndVersion.static_dict[factory_branch]

# Some factory branch names of early projects didn't follow the convention.
# Initializes the static dict with these exceptions.
_ExtractBaseboardAndVersion.static_dict = {
    'factory-zako-5220.B': ('beltino', 5220),
    'factory-monroe-5140.B': ('beltino', 5140),
    'factory-panther-4920.23.B': ('beltino', 4920),
    'factory-4455.B': ('slippy', 4455),
    'factory-skate-4262.459.B': ('daisy', 4262),
    'factory-spring-4262.B': ('daisy', 4262),
    }


def GetFactoryBranchInfo(board, base_board, repo_sync, boards_yaml=None):
  """Gets factory branch info.

  Gets factory branch info for a board, or all boards based on the base_board,
  or all boards if both board and base_board are None.

  Args:
    board: The board name to get its factory branch info.
    base_board: The base board name to get factory branches info for
        all boards base on the base_board.
    repo_sync: whether to 'repo sync' in platform/chromeos-hwid repo.
    boards_yaml: A local yaml file specifying factory branch info for
        all boards.

  Returns: A list of tuples (board name, factory branch name) sorted by
      factory branch version and group by base board.
  """
  if boards_yaml:
    boards_info = yaml.load(open(boards_yaml))
  else:
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform', 'chromeos-hwid')
    if not os.path.exists(hwid_dir):
      logging.error('No %s in source tree.', hwid_dir)
      sys.exit(1)

    # Do repo sync -n (fetch only, don't update working tree).
    if repo_sync:
      process_utils.Spawn(
          'repo sync -n .',
          log=True, cwd=hwid_dir, shell=True, check_call=True)

    # Always read boards.yaml from ToT as all boards are required to have an
    # entry in it.
    boards_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', 'remotes/cros-internal/master:boards.yaml'],
        cwd=hwid_dir))

  def _LogBaseboardMaxVersion(branch_name, max_version):
    base_board, version = _ExtractBaseboardAndVersion(branch_name)
    if base_board in max_version and version < max_version[base_board]:
      return
    else:
      max_version[base_board] = version

  board_branch_list = []
  base_board_max_version = {}
  for b in boards_info.itervalues():
    # Only get branch info for boards using v3 HWID.
    if 'version' in b and b['version'] != 3:
      continue

    if board:
      if b['board'] == board.upper():
        return [(b['board'], b['branch'])]
    elif base_board:
      # Factory branch should contain base board name.
      if base_board.lower() in b['branch']:
        board_branch_list.append((b['board'], b['branch']))
        _LogBaseboardMaxVersion(b['branch'], base_board_max_version)
    else:
      board_branch_list.append((b['board'], b['branch']))
      _LogBaseboardMaxVersion(b['branch'], base_board_max_version)

  def _key_func(b):
    # Sort by two keys:
    #   - The max factory version of the base board: group by base board.
    #   - The factory branch version: list new projects first.
    #
    # Examples:
    #   rambi   factory-rambi-6420.B.
    #   squawks factory-rambi-5517.B.
    #   pi      factory-pit-5499.B
    base_board, version = _ExtractBaseboardAndVersion(b[1])
    return(base_board_max_version[base_board], version)

  # Reversely sort the list by the above two keys.
  return sorted(board_branch_list, key=_key_func, reverse=True)


def OutputBundleInfo(boards_branch_info, html_file, sync):
  """Print factory bundle information.

  Args:
    boards_branch_info: A list of tuples, each tuple is (board, factory_branch)
        containing the board name and its factory branch name.
    html_file: File name to store the output in HTML format.
    sync: Whether to sync codebase to get the latest info.
  """
  output_lines = [BundleFields]
  for board, branch in boards_branch_info:
    bundle_info = _GetFactoryBundleInfo(board, branch, sync)
    if bundle_info is not None:
      output_lines.append(list(bundle_info))

  if html_file is None:
    num_columns = len(output_lines[0])
    # Calculate maximum length of each column.
    max_lengths = []
    for column_no in xrange(num_columns):
      max_lengths.append(max(len(line[column_no]) for line in output_lines))

    # Print each line, padding as necessary to the max column length.
    for line in output_lines:
      for column_no in xrange(num_columns):
        sys.stdout.write(line[column_no].ljust(max_lengths[column_no] + 2))
      sys.stdout.write('\n')
  else:
    def _ConvertToHTMLRow(line):
      html_row = ''
      for item in line:
        html_row += '<td>' + item + '</td>'
      return '<tr>' + html_row + '</tr>'

    html_rows = map(_ConvertToHTMLRow, output_lines)
    table_style = ('style="border:2px solid; font-size: 26px" '
                   'rules="all" cellpadding="5"')
    html_table = ('<table ' + table_style + '>\n' +
                  '\n'.join(html_rows) +
                  '</table>\n')
    footnote = (
        '<pre style="font-size: 20px">\n'
        'The table is generated from the bundle README files under board '
        'private overlay in different factory branches.\n'
        'The file "chromeos-base/chromeos-factory-board/files/bundle/README" '
        'is automatically generated by "src/platform/factory/bin/'
        'finalize_bundle" when a bundle master prepares a factory bundle.\n\n'
        'If you found the info is outdated, please update the README file and '
        'run script "src/platform/factory-private/sh/update_bundle_info.sh" to '
        'regenerate the table.\n'
        '</pre>')

    file_utils.WriteFile(html_file, html_table + footnote)


def ParseArgs():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      epilog=EXAMPLES,
      formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument('--board', '-b',
                      help='The board name to get factory bundle info.')
  parser.add_argument('--base_board', '-bb',
                      help=('The base board name to get factory bundle info\n'
                            'for all boards based on the base board.'))
  parser.add_argument('--html_file', '-f',
                      help='File name to store the output in HTML format.')
  parser.add_argument('--boards_yaml', '-by',
                      help=('A local boards.yaml file storing factory branch\n'
                            'info for all boards. An example of boards.yaml:\n'
                            'SQUAWKS:\n'
                            '    board: SQUAWKS\n'
                            '    branch: factory-rambi-5517.B\n'
                            'CANDY:\n'
                            '    board: CANDY\n'
                            '    branch: factory-rambi-6420.B\n'))
  parser.add_argument('--no-sync', action='store_false', dest='sync',
                      help=('Don\'t run repo sync in platform/chromeos-hwid '
                            'repo and board private overlays.'))
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation to repo sync.")

  return parser.parse_args()


def main():
  args = ParseArgs()
  if not args.yes and args.sync:
    answer = raw_input('*** repo sync will be invoked in platform/'
                       'chromeos-hwid repo and board private overlays.\n'
                       '*** Continue? [y/N] ')
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')
  boards_branch_info = GetFactoryBranchInfo(
      args.board, args.base_board, args.sync, args.boards_yaml)
  OutputBundleInfo(boards_branch_info, args.html_file, args.sync)


if __name__ == '__main__':
  main()
