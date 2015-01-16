#!/usr/bin/python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Analyzes test results in USB drive written by factory_CameraPerformanceAls in
Module-level and AB Covers camera testing.

This file must be able to run standalone without Chrome OS system. For example,
it should run with ActivePython on MS-Windows. The external library dependency
is kept as minimum as possible.
"""

import argparse
from collections import defaultdict, namedtuple, OrderedDict
import csv
import glob
import numpy as np
import os
import re

# default filename of exported CSV file
_DEFAULT_CSV_FILE = 'result.csv'

# field names in CSV file
_FIELDS = ['Serial', 'Result', 'Firmware', 'Camera_Init', 'Camera_Image',
           'VisualCorrectness', 'LensShading', 'MTF',
           'MedianMTF', 'LowestMTF', 'Shift',
           'Shift_X', 'Shift_Y', 'Tilt', 'LensShading']

# serial numbers to ignore
_SN_BLACKLIST = ['NO_SN', 'INVALID_SN']

# Data structure for test pass criteria. Min_value and max_value are floats or
# None. At least one of min_value and max_value must be None.
Criteria = namedtuple('Criteria',
                      ['display_name', 'min_value', 'max_value'])

# ordered dictionary of format field-name => criteria
_PASS_CRITERIA = OrderedDict([
    ('MedianMTF', Criteria('Median MTF', 0.240, None)),
    ('LowestMTF', Criteria('Lowest MTF', 0.145, None)),
    ('Shift', Criteria('Shift Ratio', None, 0.045)),
    ('Shift_X', Criteria('X Shift (pixels)', None, None)),
    ('Shift_Y', Criteria('Y Shift (pixels)', None, None)),
    ('Tilt', Criteria('Tilt (degrees)', None, 1.0)),
    ('LensShading', Criteria('Lens Shading Ratio', 0.60, None))])

# Format to parsing the text file. List of (field-name, regexp-match-pattern).
_TEXT_FILE_FORMAT = [
    ('Result', r"'cam_end': *([^,]+),"),
    ('Firmware', r"'cam_fw': *([^,]+),"),
    ('Camera_Init', r"'cam_init': *([^,]+),"),
    ('Camera_Image', r"'cam_img': *([^,]+),"),
    ('VisualCorrectness', r"'cam_vc': *([^,]+),"),
    ('LensShading', r"'cam_ls': *([^,]+),"),
    ('MTF', r"'cam_mtf': *([^,]+),"),

    ('MedianMTF', r'^Median MTF value:\s*(\S+)$'),
    ('LowestMTF', r'^Lowest MTF value:\s*(\S+)$'),
    ('Shift', r'^Image shift percentage:\s*(\S+)$'),
    ('Shift_X', r'^Image shift X:\s*(\S+)$'),
    ('Shift_Y', r'^Image shift Y:\s*(\S+)$'),
    ('Tilt', r'^Image tilt:\s*(\S+)$'),
    ('LensShading', r'^Lens shading ratio:\s*(\S+)$')]


def _Percent(a, b):
  """Returns:

     Floating percentage of a / b.
  """
  return 100.0 * a / b


def _PrintStatistics(values, criteria):
  """Calculates statistics on a list of values accroding to given criteria.

  Args:
    values: a list of numeric values.
    criteria: Criteria object.

  Returns:
    Floating percentage of a / b.
  """
  display_name = criteria.display_name
  min_value = criteria.min_value
  max_value = criteria.max_value

  total_count = len(values)
  assert min_value == None or max_value == None
  if min_value:
    failed_count = len(filter((lambda x: abs(x) < min_value), values))
    failed_condition = '< %.3f' % min_value
  elif max_value:
    failed_count = len(filter((lambda x: abs(x) > max_value), values))
    failed_condition = '> %.3f' % max_value
  else:
    failed_condition = None

  print(display_name + ':')
  print('    Average: %.3f' % np.average(values))
  print('    Median: %.3f' % np.median(values))
  print('    Std deviation: %.3f' % np.std(values))
  print('    Range: (%.3f - %.3f)' % (np.min(values), np.max(values)))
  if failed_condition:
    print('    %s: %d/%d (%.1f%%)' % (failed_condition, failed_count,
                                      total_count,
                                      _Percent(failed_count, total_count)))


def AnalyzeData(data_list):
  """Anaylzes data and print the summary.

  Args:
    data_list: A list of dictionaries. Each contains the results of one DUT.

  Returns:
    A list of dictionaries, where each contains the results of one DUT.
  """
  numeric_pattern = re.compile(r'^[+\-]?[0-9.]+$')
  data_count = len(data_list)
  if data_count == 0:
    print('No test data is found')
    return

  values = defaultdict(list)
  for row in data_list:
    for field in _FIELDS:
      if row[field] == 'N/A':
        # Skip it directly. Statistics like avg won't take it into account.
        continue
      if numeric_pattern.match(row[field]):
        v = float(row[field])
      else:
        v = row[field]
      values[field].append(v)

  # Passed/ Failed
  passed_count = values['Result'].count('PASSED')
  failed_count = values['Result'].count('FAILED')
  assert passed_count + failed_count == data_count
  print('Passed: %d/%d (%.1f%%)' % (passed_count,
                                    data_count,
                                    _Percent(passed_count, data_count)))
  print('Failed: %d/%d (%.1f%%)' % (failed_count,
                                    data_count,
                                    _Percent(failed_count, data_count)))

  for field, criteria in _PASS_CRITERIA.iteritems():
    _PrintStatistics(values[field], criteria)


def CollectDataAndExportCSV(data_path, csv_filename):
  """Reads all .txt files in the current folder, and exports its data to
  returned data structure and csv_filename.

  Args:
    data_path: source data path (None if using the current working directory)
    csv_filename: output filename of CSV file (None if no CSV file is needed)

  Returns:
    A list of dictionaries, where each contains the results of one DUT.
  """
  data_dict = defaultdict(dict)

  def _read_attr(lines, attr, pattern, fallback='N/A'):
    matches = [re.search(pattern, l).group(1)
               for l in lines if re.search(pattern, l)]
    if not matches:
      data_dict[sn][attr] = fallback
    else:
      data_dict[sn][attr] = matches[-1]

  if data_path:
    glob_pattern = os.path.join(data_path, '*.txt')
  else:
    glob_pattern = '*.txt'

  for txt_file in glob.glob(glob_pattern):
    sn = re.match(r'^(.*)\.txt$', txt_file).group(1)
    data_dict[sn]['Serial'] = sn

    with open(txt_file, 'r') as txt:
      lines = txt.read().splitlines()

      for field, pattern in _TEXT_FILE_FORMAT:
        _read_attr(lines, field, pattern)

  # Export data_dict to CSV file
  fields_dict = OrderedDict([(f, f) for f in _FIELDS])

  if csv_filename:
    with open(csv_filename, 'w') as csvfile:
      writer = csv.DictWriter(csvfile, fields_dict)
      writer.writeheader()
      for sn in sorted(data_dict.keys()):
        writer.writerow(data_dict[sn])

  return [data for sn, data in data_dict.iteritems()]


def main():
  """Main routine."""
  prog_desc = """Analyze test data collected from IQ test of camera fixtures.

The test results for each DUT are stored in a single text file
([SerialNumber].txt) on USB drive or aux_logs folder in Shopfloor. This program
can find all text files under one directory and analyze the results. The results
are also written to a CSV file, which can be imported in spreadsheet
software later. """

  parser = argparse.ArgumentParser(
      description=prog_desc)
  parser.add_argument('--data-path', '-d', dest='data_path',
                      help='source data path '
                      '(default: current working directory)')
  parser.add_argument('--csv-file', '-f', dest='csv_filename',
                      default=_DEFAULT_CSV_FILE,
                      help='output filename of the CSV file '
                      '(default: %s)' % _DEFAULT_CSV_FILE)
  parser.add_argument('--no-csv', action='store_false', dest='export_csv',
                      help='disable output of CSV file')
  args = parser.parse_args()

  data_list = CollectDataAndExportCSV(
      args.data_path, args.csv_filename if args.export_csv else None)
  AnalyzeData(data_list)


if __name__ == '__main__':
  main()
