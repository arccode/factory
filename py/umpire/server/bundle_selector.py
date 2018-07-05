# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles /webapps/resourcemap requests.

According to DUT (device under test) info embedded in request header, it
chooses the right bundle for the DUT and returns the resource map of the bundle.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common


def SelectRuleset(config, dut_info):
  """Gets ruleset for the DUT based on rulesets defined in UmpireConfig.

  Args:
    config: an UmpireConfig object
    dut_info: a DUT info represented in key-value dict. It should be parsed
        from X-Umpire-DUT header by webapp_utils.ParseDUTHeader().

  Returns:
    ruleset; None if no ruleset is matched.
  """

  def TryScalarMatcher(name, expect_values):
    """Checks if the DUT matches if name is a scalar matcher.

    For a scalar matcher, a DUT is matched if dut_info[name] is in
    expected_values.

    Args:
      name: matcher name
      expect_values: list/set of scalar values to match

    Returns:
      True if name is not a scalar matcher.
      Otherwise, True if the DUT matches the matcher.
    """
    if name not in common.SCALAR_MATCHERS:
      return True
    return dut_info.get(name) in expect_values

  def TryScalarPrefixMatcher(name, expect_values):
    """Checks if the DUT matches if name is a scalar-prefix matcher.

    For a scalar-prefix matcher, a DUT is matched if the DUT info has a
    property which's key starts with name and value is in values.

    Args:
      name: matcher name
      expect_values: list/set of scalar values to match

    Returns:
      True if name is not a scalar_prefix matcher.
      Otherwise, True if the DUT matches the matcher.
    """
    if name not in common.SCALAR_PREFIX_MATCHERS:
      return True
    return any(dut_info[k] in expect_values for k in dut_info
               if k.startswith(name))

  def TryRangeMatcher(name, value_range):
    """Checks if the DUT matches if name is a range matcher.

    For a scalar matcher, a DUT is matched if dut_info[key] is within
    value_range, where key is matcher's name without '_range' postfix.

    Args:
      name: range matcher, which ends with '_range'
      value_range: (range_start, range_end). '-' means open end.

    Returns:
      True if name is not a range matcher.
      Otherwise, True if the DUT matches the matcher.
    """
    if name not in common.RANGE_MATCHERS:
      return True
    dut_value = dut_info.get(name[:-6])  # remove '_range' postfix
    if dut_value is None:
      return False
    (start, end) = value_range
    return ((start == '-' or start <= dut_value) and
            (end == '-' or end >= dut_value))

  # Check ruleset in order.
  for ruleset in config['rulesets']:
    if not ruleset['active']:
      continue
    # If no matcher is provided, it matches all.
    if 'match' not in ruleset:
      return ruleset
    # Rules in a ruleset are ANDed, i.e. the DUT needs to match all of them.
    if all(TryScalarMatcher(name, value) and
           TryScalarPrefixMatcher(name, value) and
           TryRangeMatcher(name, value)
           for name, value in ruleset['match'].iteritems()):
      return ruleset
  return None


def SelectBundle(config, dut_info):
  """Gets bundle ID for the DUT based on rulesets defined in UmpireConfig.

  Args:
    config: an UmpireConfig object
    dut_info: a DUT info represented in key-value dict. It should be parsed
        from X-Umpire-DUT header by webapp_utils.ParseDUTHeader().

  Returns:
    Bundle ID; None if no ruleset is matched.
  """
  ruleset = SelectRuleset(config, dut_info)
  return ruleset['bundle_id'] if ruleset else None


def GetResourceMap(dut_info, env):
  """Gets resource map for the DUT.

  It is used for twisted to call when receiving "GET /webapps/resourcemap"
  request.

  Args:
    dut_info: value of request header X-Umpire-DUT.
    env: an UmpireEnv object.

  Returns:
    String for response text.
  """
  result = []

  bundle_id = SelectBundle(env.config, dut_info)
  if not bundle_id:
    return None

  bundle = env.config.GetBundle(bundle_id)
  if not bundle:
    return None

  # TODO(hungte) Remove __token__ and shop_floor_handler when most DUTs have
  # finished migration.
  result = ['id: %s' % bundle['id'],
            'note: %s' % bundle['note'],
            '__token__: 00000001',
            'shop_floor_handler: /umpire',
            'payloads: %s' % bundle['payloads']]

  return ''.join('%s\n' % s for s in result)
