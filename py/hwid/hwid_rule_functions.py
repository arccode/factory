# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID specific rule function implementations."""

import collections
import itertools
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeList, MakeSet
from cros.factory.gooftool.vpd_data import KNOWN_VPD_FIELD_DATA
from cros.factory.hwid import HWIDException
from cros.factory.hwid.encoder import (
    BOMToBinaryString, BinaryStringToEncodedString)
from cros.factory.test import registration_codes
from cros.factory.rule import RuleFunction, Value, GetContext, GetLogger


def GetClassAttributesOnBOM(hwid, comp_cls):
  """Creates a set of valid rule values to be evaluated with.

  This method accepts a HWID context and a component class, and generates a dict
  of attributes under the HWID context. First it checks there is a valid
  component of the given class in the BOM by matching the probed values in the
  BOM object to the values defined in the database. Then it extracts from the
  database all feasible values that can be used in rule evaluation (e.g.
  component name, component values, labels, ... etc.), and return the values as
  a dict. A dict with name maps to None is used to represent missing components.
  For example, the valid attributes for 'storage' class may look like:

    valid_attributes = {
        'name': 'sandisk_16g',
        'value': 'Sandisk 33456',
        'labels': ['SSD', '16G']
    }

  Args:
    hwid: The HWID context to extract attributes from.
    comp_cls: The component class to retrieve values for.

  Returns:
    A dict of attributes extracted from database that can be used to represent
    or describe the given component class. None if comp_cls is invalid.
  """
  def PackProbedString(bom, comp_cls):
    return [e.probed_string for e in bom.components[comp_cls] if
            e.probed_string is not None]

  def HasCommonElement(list1, list2):
    # Use list here so that we can support regular expression Value objects
    # later easier.
    return any([v1 == v2 for v1, v2 in itertools.product(list1, list2)])

  if comp_cls not in hwid.database.components:
    GetLogger().Error('Invalid component class: %r' % comp_cls)
    return None
  # Construct a set of known values from hwid.database and hwid.bom.
  result = collections.defaultdict(list)
  bom_comp_value_list = PackProbedString(hwid.bom, comp_cls)
  for comp_name, comp_attr in (
      hwid.database.components[comp_cls].iteritems()):
    db_comp_value_list = MakeList(comp_attr['value'])
    if (bom_comp_value_list and
        HasCommonElement(db_comp_value_list, bom_comp_value_list)):
      # The probed values in BOM matches an entry in database. We have a valid
      # component here.
      result['name'].append(comp_name)
      for attr_key, attr_value in comp_attr.iteritems():
        result[attr_key].extend(MakeList(attr_value))
  # If the set is empty, add a None element indicating that the component
  # class is missing.
  if not result:
    result['name'] = None
  return result


def CreateSetFromAttributes(attr_dict):
  """Create a set from the values of the given attribute dict.

  Args:
    attr_dict: A dict of attributes.

  Returns:
    A set object with elements consisting of the values from the given attribute
    dict.
  """
  result = set()
  for attr in attr_dict.itervalues():
    result |= MakeSet(attr)
  return result


def _ComponentCompare(comp_cls, values, op_for_values):
  """Component comparison helper function.

  Args:
    comp_cls: The class of component to test.
    values: A list of values to match.
    op_for_values: The operation used to generate final result. Must be any or
        all.
  """
  context = GetContext()
  attrs = GetClassAttributesOnBOM(context.hwid, comp_cls)
  if attrs is None:
    return False
  comp_attr_set = CreateSetFromAttributes(attrs)
  values = [
      Value(v) if not isinstance(v, Value) else v for v in MakeList(values)]
  return op_for_values(
      [any([v.Matches(attr) for attr in comp_attr_set]) for v in values])


@RuleFunction(['hwid'])
def ComponentEq(comp_cls, values):
  """Test if the component equals to the values set.

  True if every value in 'values' has a match in the attributes of 'comp_cls'

  Args:
    comp_cls: The class of component to test.
    values: A list of values to match.

  Returns:
    True if the component equals to the given values, False otherwise.
  """
  return _ComponentCompare(comp_cls, values, all)


@RuleFunction(['hwid'])
def ComponentIn(comp_cls, values):
  """Test if the component is in the values set.

  True if one value in 'values' has a match in the attributes of 'comp_cls'

  Args:
    comp_cls: The class of component to test.
    values: A list of values to match.

  Returns:
    True if the component is in the given values, False otherwise.
  """
  return _ComponentCompare(comp_cls, values, any)


@RuleFunction(['hwid'])
def GetComponentAttribute(comp_cls, key):
  """A wrapper method to get component attribute value.

  Args:
    comp_cls: The component class to get attribute from.
    key: A string specifying the attribute to get.

  Returns:
    The attribute value got.
  """
  context = GetContext()
  return GetClassAttributesOnBOM(context.hwid, comp_cls)[key]


@RuleFunction(['hwid'])
def SetComponent(comp_cls, name):
  """A wrapper method to update {comp_cls: name} pair of BOM and re-generate
  'binary_string' and 'encoded_string' of the HWID context.

  Args:
    comp_cls: The component class to set.
    name: The component name to set to the given component class.
  """
  context = GetContext()
  context.hwid.bom = context.hwid.database.UpdateComponentsOfBOM(
      context.hwid.bom, {comp_cls: name})
  context.hwid.binary_string = BOMToBinaryString(context.hwid.database,
                                                 context.hwid.bom)
  context.hwid.encoded_string = BinaryStringToEncodedString(
      context.hwid.database, context.hwid.binary_string)


@RuleFunction(['hwid'])
def SetImageId(image_id):
  context = GetContext()
  if image_id not in context.hwid.database.image_id:
    raise HWIDException('Invalid image id: %r' % image_id)
  context.hwid.bom.image_id = image_id
  context.hwid.binary_string = BOMToBinaryString(context.hwid.database,
                                                 context.hwid.bom)
  context.hwid.encoded_string = BinaryStringToEncodedString(
      context.hwid.database, context.hwid.binary_string)


@RuleFunction(['device_info'])
def GetDeviceInfo(key):
  """A wrapper method to get device info from shopfloor server.

  If a dict of device info is provided in the context, return the value of 'key'
  in the given dict.

  Args:
    key: The key of the device info to get.

  Returns:
    The device info value got.
  """
  return GetContext().device_info[key]


@RuleFunction(['vpd'])
def GetVPDValue(section, key):
  """A wrapper method to get VPD values on DUT.

  If a dict of vpd is provided in the context, return the value of 'key' in
  'section' of the given dict.

  Args:
    section: The section of VPD to read value from. ('ro' or 'rw')
    key: The key of the VPD value to get.

  Returns:
    The VPD value got.
  """
  return GetContext().vpd[section][key]


@RuleFunction(['vpd'])
def ValidVPDValue(section, key):
  """A wrapper method to verify VPD value.

  Args:
    section: The section of VPD to read value from. ('ro' or 'rw')
    key: The key of the VPD value to get.

  Raises:
    HWIDException if the VPD value is invalid.
  """
  value = GetVPDValue(section, key)
  valid_values = KNOWN_VPD_FIELD_DATA.get(key, None)
  if (valid_values and value not in valid_values) or (not value):
    GetLogger().Error('Invalid VPD value %r of %r' % (value, key))
    return False
  return True


@RuleFunction([])
def CheckRegistrationCode(code):
  """A wrapper method to verify registration code.

  Args:
    code: The registration code to verify.

  Raises:
    ValueError if the code is invalid.
  """
  registration_codes.CheckRegistrationCode(code)
