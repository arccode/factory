# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides functions to convert CSV (Comma Separated Values)
files to YAML format as part of factory parameters generation.

Although YAML is powerful, we can still take advantage of incorporating with
other existing tools in CSV format. CSV files will be treated in two
pre-defined types - dict and list of dict, depending on its columns. Each cell
in CSV file is assumed to be a python evaluable syntax, which nearly no
difference in text format for primitive types like int, float, str ...etc.
More details and examples are demonstrated in the unittest.
"""

import csv
import logging
import os

KEY = '__key__'
VALUE = '__value__'


class CsvLink:
  """Special wrapper class for identifying an external link in cell."""

  def __init__(self, link=None):
    self.link = link

  def __eq__(self, rhs):
    return self.link == rhs.link


def ReadSingleCell(value):
  """Converts a single cell to a python object.

  The value must be a python evaluable string, otherwise, exception
  will be raised by eval() function.  If the special object, CsvLink,
  was detected, reading will be proceeded recursively.
  """
  if value == '':
    return None
  value_in_python = eval(value)  # pylint: disable=eval-used
  # Recursive reading
  if isinstance(value_in_python, CsvLink):
    try:
      value_in_python = ReadCsv(value_in_python.link)
    except Exception as e:
      raise ValueError('Failed to load external csv - %s, %s' %
                       (value_in_python.link, e))
  return value_in_python


def IsAnnotation(row_in_dict, fieldnames):
  """Returns if a row is an annotaion.

  Annotation is defined pretty much in python style. If every cell in the row
  is empty length or the first cell begins with a hash character (#), it is
  considered as an annotation line.

  Args:
    row_in_dict: the dict object represents a single row by DictReader.next().
    fieldnames: the list object represents the first row in
        DictReader.fieldnames
  """
  # Ignore a row if it starts with pound character.
  if row_in_dict.get(fieldnames[0], '').startswith('#'):
    return True

  for key in fieldnames:
    if row_in_dict.get(key, '') != '':
      return False

  return True


def IsCsvADictHeader(source):
  """Reads its first row and see if it fits the pre-defined format."""
  with open(source, 'r') as fd:
    reader = csv.DictReader(fd)
    fieldnames = reader.fieldnames
    # Check fieldnames.
    if fieldnames != [KEY, VALUE]:
      return False
  return True


def ReadCsvAsDict(source):
  """Reads a csv and converts to python dict.

  A dict formatted csv have only two columns: __key__ and __value__.
  """
  data = {}
  with open(source, 'r') as fd:
    reader = csv.DictReader(fd)
    fieldnames = reader.fieldnames
    # Check fieldnames.
    if fieldnames != [KEY, VALUE]:
      raise ValueError('Columns format is not a dict in %s' % source)
    for idx, row in enumerate(reader):
      if IsAnnotation(row, fieldnames):
        continue

      key = row.get(KEY)
      if key in data:
        raise ValueError('Duplicated key %s in %s' % (key, source))

      value = ReadSingleCell(row.get(VALUE, ''))
      data[key] = value
      # Check if any fields left
      if len(row) > 2:
        raise ValueError('Unexpectecd data at row %d' % idx)
  return data


def ReadCsvAsListOfDict(source):
  """Reads csv and treat it as a list of dict.

  The dict's key will follow the column in first row.
  """
  data = []
  with open(source, 'r') as fd:
    reader = csv.DictReader(fd)
    fieldnames = reader.fieldnames

    # Check if fieldnames are unique.
    if len(set(fieldnames)) != len(fieldnames):
      raise ValueError('Duplicated column name in %s' % source)

    for idx, row in enumerate(reader):
      if IsAnnotation(row, fieldnames):
        continue
      converted_dict = {}
      # Check if there are dangling cell.
      if None in row:
        logging.debug(
            'Cell without a column name is ignored during conversion\n'
            'Row[%d] - %s', idx, row[None])
      for key in fieldnames:
        converted_dict[key] = ReadSingleCell(row.get(key, ''))
      data.append(converted_dict)
  return data


def ReadCsv(source):
  """Reads a csv from source and returns as a python object."""
  original_directory = os.getcwd()
  source = os.path.abspath(source)
  os.chdir(os.path.dirname(source))
  # Try dict first, because dict is a subset of list of dict.
  try:
    if IsCsvADictHeader(source):
      ret = ReadCsvAsDict(source)
    else:
      ret = ReadCsvAsListOfDict(source)
  finally:
    os.chdir(original_directory)
  return ret
