#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of HWID v3 rule evaluator."""

import re
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeSet
from cros.factory.hwid import HWIDException


class RuleEvaluator(object):
  """A utility class to evaluate HWID v3 rules under the given HWID context."""
  @classmethod
  def _ConvertYamlStringToSet(cls, yaml_string):
    """Converts yaml_string '(a, b, c)' to set(['a', 'b', 'c']) and 'a' to
    set(['a']).

    Args:
      yaml_string: A YAML string optionally enclosed by parentheses.

    Returns:
      A set parsed from the YAML string.
    """
    SET = re.compile(r'\((.+)\)')
    yaml_string = yaml_string.strip()
    elements = SET.findall(yaml_string)
    if not elements:
      return set([yaml_string])
    return set([e.strip() for e in elements[0].split(',')])

  @classmethod
  def CheckAll(cls, hwid, check_all_list):
    """Recursively checks if all of the conditions in the given list are True
    under the given HWID context.

    Args:
      hwid: A HWID object.
      check_all_list: A list of conditions.

    Returns:
      True if all of the conditions are satisfied, False otherwise.

    Raises:
      HWIDException if the rule syntax is invalid.
    """
    for condition in check_all_list:
      if isinstance(condition, dict):
        # Nested check_all or check_any.
        if len(condition) != 1:
          raise HWIDException('Invalid rule syntax: Multiple check_all or '
                              'check_any in one condition.')
        for op, cond in condition.iteritems():
          if op.upper() == 'CHECK_ALL':
            if not cls.CheckAll(hwid, cond):
              return False
          elif op.upper() == 'CHECK_ANY':
            if not cls.CheckAny(hwid, cond):
              return False
          else:
            raise HWIDException('Invalid operator: %s.' % op)
      else:
        if not cls.CheckCondition(hwid, condition):
          return False
    return True

  @classmethod
  def CheckAny(cls, hwid, check_any_list):
    """Recursively checks if any of the conditions in the given list is True
    under the given HWID context.

    Args:
      hwid: A HWID object.
      check_any_list: A list of conditions.

    Returns:
      True if any of the conditions is satisfied, False otherwise.

    Raises:
      HWIDException is the rule syntax is invalid.
    """
    for condition in check_any_list:
      if isinstance(condition, dict):
        # Nested check_all or check_any.
        if len(condition) != 1:
          raise HWIDException('Invalid rule syntax: Only one check_all or '
                              'check_any in one condition is allowed.')
        for op, cond in condition.iteritems():
          if op.upper() == 'CHECK_ALL':
            if cls.CheckAll(hwid, cond):
              return True
          elif op.upper() == 'CHECK_ANY':
            if cls.CheckAny(hwid, cond):
              return True
          else:
            raise HWIDException('Invalid operator: %s.' % op)
      else:
        if cls.CheckCondition(hwid, condition):
          return True
    return False

  @classmethod
  def CheckCondition(cls, hwid, condition):
    """Checks if the give condition is True under the given HWID context.

    Args:
      hwid: A HWID object.
      condition: A string representing a HWID v3 condition.

    Returns:
      True is the condition is met, False otherwise.

    Raises:
      HWIDException if the rule syntax is invalid.
    """
    def CreateSetFromAttributes(attr_dict):
      ret = set()
      for name, attr in attr_dict.iteritems():
        ret |= set([name])
        if attr is not None:
          for key in ['value', 'labels']:
            if key in attr:
              ret |= MakeSet(attr[key])
      return ret

    comp_cls, operator, expected_value = condition.split(None, 2)

    # Return False if the component class of interest is either not in the BOM
    # or not in the database.
    if (comp_cls not in hwid.bom.components or
        comp_cls not in hwid.database.components):
      return False

    # Construct a set of known values from hwid.database and hwid.bom.
    known_values = set()
    for comp_name, comp_attr in hwid.database.components[comp_cls].iteritems():
      db_comp_value_set = MakeSet(comp_attr['value'])
      def PackProbedString(bom, comp_cls):
        return [e.probed_string for e in bom.components[comp_cls] if
                e.probed_string is not None]
      bom_comp_value_set = MakeSet(PackProbedString(hwid.bom, comp_cls))
      if (bom_comp_value_set and
          db_comp_value_set <= bom_comp_value_set):
        known_values |= CreateSetFromAttributes({comp_name: comp_attr})
    # If the set is empty, add a 'None' element indicating that the component
    # class is missing.
    if not known_values:
      known_values |= set(['None'])

    # Construct a set of target values to compare with.
    target_values = set()
    if expected_value.strip() == '*':
      target_values = CreateSetFromAttributes(
          hwid.database.components[comp_cls])
    else:
      target_values = cls._ConvertYamlStringToSet(expected_value)

    # The calculations...
    operator = operator.upper()
    if operator == 'EQ':
      if target_values & known_values == target_values:
        return True
      return False
    elif operator == 'IN':
      if target_values & known_values:
        return True
      return False
    elif operator == 'NE':
      if target_values & known_values == target_values:
        return False
      return True
    elif operator == 'NOT_IN':
      if target_values & known_values:
        return False
      return True
    else:
      raise HWIDException('Invalid operator: %s.' % operator)

  @classmethod
  def EvaluateRules(cls, hwid, rules):
    """Evaluates the give rules under the given HWID context.

    Args:
      hwid: A HWID object.
      rules: A list of rules to evaluate.

    Returns:
      A tuple of three lists of strings in the order of ([rules_passed],
      [rules_not_evaluated], [rules_failed]), which include the rules that
      passed, not evaluated due to 'when' not satisfied, and rules that
      failed under the given HWID context.

    Raises:
      HWIDException if invalid rule is encountered.
    """
    passed = []
    not_evaluated = []
    failed = []
    for r in rules:
      if ((len(r['when']) == 1 and r['when'][0].strip() == '*') or
          cls.CheckAll(hwid, r['when'])):
        # A list with one '*' in 'when' means always true.
        if 'check_all' in r:
          if cls.CheckAll(hwid, r['check_all']):
            passed.append(r['name'])
          else:
            failed.append(r['name'])
        elif 'check_any' in r:
          if cls.CheckAny(hwid, r['check_any']):
            passed.append(r['name'])
          else:
            failed.append(r['name'])
        else:
          raise HWIDException('Invalid rule: %s.' % r['name'])
      else:
        not_evaluated.append(r['name'])
    return (passed, not_evaluated, failed)

  @classmethod
  def VerifySKU(cls, hwid, allowed_skus):
    """Checks if the HWID under the given belongs to any of the given allowed
    SKUs.

    Args:
      hwid: A HWID object.
      allowed_skus: A list of allowed SKUs to check against.

    Returns:
      A list of strings indicating the SKUs that the HWID satisfies.
    """
    return [s['name'] for s in allowed_skus
            if cls.CheckAll(hwid, s['check_all'])]
