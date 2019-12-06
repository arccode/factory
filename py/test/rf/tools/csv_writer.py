# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides help functions to write CSV (Comma Separated Values)
files.
"""

import csv
import logging
import pprint


def WriteCsv(target, list_of_dict, key_orders):
  """Writes a list of dict to a CSV file.

  The columns' order are assigned by key_orders. For columns that is not
  listed in key_orders, their order are not guaranteed.

  Args:
    target: the file path of output csv.
    list_of_dict: a list of dicts converts to CSV. Every single dict will
        contributed as a single row in the CSV.
    key_orders: columns' order from left to right.
  """
  # Scaning over list_of_dict to extract all the columns.
  fieldnames = set()
  for dict_obj in list_of_dict:
    fieldnames.update(set(dict_obj.keys()))

  # Prepare the fieldnames to pass into DictWriter.
  for key in key_orders:
    fieldnames.discard(key)
  for key in fieldnames:
    key_orders.append(key)

  logging.debug('Determined key_orders = \n%s\n', pprint.pformat(key_orders))

  with open(target, 'w') as fd:
    writer = csv.DictWriter(fd, key_orders)
    # Workaround for python before 2.7 that doesn't have a writer.writeheader
    header_dict = {}
    for key in key_orders:
      header_dict[key] = key
    writer.writerow(header_dict)

    for dict_obj in list_of_dict:
      writer.writerow(dict_obj)
