# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functions across different RF related tests."""

import logging
import math
import os

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.shopfloor import GetShopfloorConnection

def IsInRange(observed, threshold_min, threshold_max):
  """Returns True if threshold_min <= observed <= threshold_max.

  If either thresholds are None, then the comparison will always succeed.
  If observed be one of nan, inf or None, False will be returned.
  """
  if observed is None or math.isnan(observed) or math.isinf(observed):
    return False
  if threshold_min is not None and observed < threshold_min:
    return False
  if threshold_max is not None and observed > threshold_max:
    return False
  return True

def FormattedPower(power, format_str='%7.2f'):
  """Returns a formatted power while allowing power be a None."""
  return 'None' if power is None else (format_str % power)

def CheckPower(measurement_name, power, threshold, failures, prefix='Power'):
  '''Simple wrapper to check and display related messages.

  Args:
    measurement_name: name for logging.
    power: power value to check.
    threshold: a tuple in (min, max) format.
    failures: a list to append if power is out of spec.
    prefix: additonal annotation for logging.

  Returns:
    True if power is in range, else False.
  '''
  min_power, max_power = threshold
  if not IsInRange(power, min_power, max_power):
    failure = '%s for %r is %s, out of range (%s,%s)' % (
        prefix, measurement_name, FormattedPower(power),
        FormattedPower(min_power), FormattedPower(max_power))
    factory.console.info(failure)
    failures.append(failure)
    return False

  factory.console.info('%s for %r is %s',
      prefix, measurement_name, FormattedPower(power))
  return True


def DownloadParameters(parameters, local_cache_dir):
  """Downloads parameters from shopfloor and saved to state/caches.

  Args:
    parameters: A list of regular expressions indicates parameters
        to download from shopfloor server.
    local_cache_dir: The path of the root directory to save downloaded
        parameters.
  """
  factory.console.info('Start downloading parameters...')
  shopfloor_client = GetShopfloorConnection()
  logging.info('Syncing time with shopfloor...')
  goofy = factory.get_state_instance()
  goofy.SyncTimeWithShopfloorServer()

  download_list = []
  for glob_expression in parameters:
    logging.info('Listing %s', glob_expression)
    download_list.extend(
        shopfloor_client.ListParameters(glob_expression))
  logging.info('Download list prepared:\n%s', '\n'.join(download_list))
  assert len(download_list) > 0, 'No parameters found on shopfloor'
  # Download the list and saved to caches in state directory.
  for filepath in download_list:
    utils.TryMakeDirs(os.path.join(
        local_cache_dir, os.path.dirname(filepath)))
    binary_obj = shopfloor_client.GetParameter(filepath)
    with open(os.path.join(local_cache_dir, filepath), 'wb') as fd:
      fd.write(binary_obj.data)
  # TODO(itspeter): Verify the signature of parameters.
