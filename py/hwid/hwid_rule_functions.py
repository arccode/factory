# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID specific rule function implementations."""

import factory_common # pylint: disable=W0611

from cros.factory.common import MakeList, MakeSet
from cros.factory.gooftool.vpd_data import KNOWN_VPD_FIELD_DATA
from cros.factory.hwid.common import HWIDException
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
        'labels': {
            'technology': 'SSD',
            'size': '16G'
        }
    }

  Args:
    hwid: The HWID context to extract attributes from.
    comp_cls: The component class to retrieve values for.

  Returns:
    A dict of attributes extracted from database that can be used to represent
    or describe the given component class. None if comp_cls is invalid.
  """
  def PackProbedValues(bom, comp_cls):
    results = []
    for c in bom.components[comp_cls]:
      if c.probed_values is None:
        continue
      matched_component = hwid.database.components.MatchComponentsFromValues(
          comp_cls, c.probed_values)
      if matched_component:
        results.extend(matched_component.keys())
    return results

  if comp_cls not in hwid.database.components.GetRequiredComponents():
    GetLogger().Error('Invalid component class: %r' % comp_cls)
    return None
  # Construct a set of known values from hwid.database and hwid.bom.
  results = []
  bom_components = PackProbedValues(hwid.bom, comp_cls)
  for comp in bom_components:
    try:
      comp_attrs = hwid.database.components.GetComponentAttributes(comp_cls,
                                                                   comp)
      results.append(comp)
      if 'labels' in comp_attrs:
        results.extend(MakeList(comp_attrs['labels'].values()))
    except HWIDException:
      continue
  # If the set is empty, add a None element indicating that the component
  # class is missing.
  if not results:
    results.append(None)
  return results


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
  values = [
      Value(v) if not isinstance(v, Value) else v for v in MakeList(values)]
  return op_for_values(
      [any([v.Matches(attr) for attr in attrs]) for v in values])


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
  """A function to set the image id of the given HWID context.

  Args:
    image_id: The image id to set.
  """
  context = GetContext()
  if isinstance(image_id, str):
    # Convert image_id string to its corresponding encoded value.
    reversed_image_id_dict = dict((value, key) for key, value in
                                  context.hwid.database.image_id.iteritems())
    if image_id not in reversed_image_id_dict:
      raise HWIDException('Invalid image id: %r' % image_id)
    image_id = reversed_image_id_dict[image_id]

  if image_id not in context.hwid.database.image_id:
    raise HWIDException('Invalid image id: %r' % image_id)
  context.hwid.bom.image_id = image_id
  context.hwid.binary_string = BOMToBinaryString(context.hwid.database,
                                                 context.hwid.bom)
  context.hwid.encoded_string = BinaryStringToEncodedString(
      context.hwid.database, context.hwid.binary_string)


@RuleFunction(['hwid'])
def GetOperationMode():
  """A function to get the set of operation modes of the HWID context.

  Returns:
    The set of operations modes currently enabled on the given HWID context.
  """
  return GetContext().hwid.mode

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
