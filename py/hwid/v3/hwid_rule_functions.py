# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID specific rule function implementations."""

import factory_common  # pylint: disable=W0611

from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3.rule import GetContext
from cros.factory.hwid.v3.rule import RuleFunction
from cros.factory.hwid.v3.rule import Value
from cros.factory.test.rules import phase
from cros.factory.utils import type_utils


def _ComponentCompare(comp_cls, values, op_for_values):
  """Component comparison helper function.

  Args:
    comp_cls: The class of component to test.
    values: A list of values to match.
    op_for_values: The operation used to generate final result. Must be any or
        all.
  """
  def _IsMatch(value):
    return any(
        [value.Matches(name) for name in context.bom.components[comp_cls]])

  context = GetContext()

  # Always treat as comparing failed if the specified component class is not
  # recorded in the BOM object.
  if comp_cls not in context.bom.components:
    return False

  values = [Value(v) if not isinstance(v, Value) else v
            for v in type_utils.MakeList(values)]
  return op_for_values([_IsMatch(v) for v in values])


@RuleFunction(['bom', 'database'])
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


@RuleFunction(['bom', 'database'])
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


@RuleFunction(['bom', 'database'])
def SetComponent(comp_cls, names):
  """Set the component of the given component class recorded in the BOM object.

  Args:
    comp_cls: The component class to set.
    names: The component name to set to the given component class.
  """
  context = GetContext()

  if not isinstance(comp_cls, str):
    raise HWIDException(
        'Component class should be in string type, but got %r.' % comp_cls)

  names = [] if names is None else type_utils.MakeList(names)
  for name in names:
    if not isinstance(name, str):
      raise HWIDException(
          'Component name should be in string type, but got %r.' % name)

  context.bom.SetComponent(comp_cls, names)


@RuleFunction(['bom', 'database'])
def SetImageId(image_id):
  """A function to set the image id of the given HWID context.

  Args:
    image_id: The image id to set.
  """
  context = GetContext()
  if isinstance(image_id, str):
    # Convert image_id string to its corresponding encoded value.
    reversed_image_id_dict = dict((value, key) for key, value in
                                  context.database.image_id.iteritems())
    if image_id not in reversed_image_id_dict:
      raise HWIDException('Invalid image id: %r' % image_id)
    image_id = reversed_image_id_dict[image_id]

  if image_id not in context.database.image_id:
    raise HWIDException('Invalid image id: %r' % image_id)
  context.bom.image_id = image_id


@RuleFunction(['bom'])
def GetImageId():
  """A function to get the image id from the given HWID context.

  Returns:
    The image id of the HWID context.
  """
  return GetContext().bom.image_id


@RuleFunction(['mode'])
def GetOperationMode():
  """A function to get the set of operation modes of the HWID context.

  Returns:
    The set of operations modes currently enabled on the given HWID context.
  """
  return GetContext().mode


@RuleFunction(['device_info'])
def GetDeviceInfo(key, default=None):
  """A wrapper method to get device info from shopfloor server.

  If a dict of device info is provided in the context, return the value of 'key'
  in the given dict.

  Args:
    key: The key of the device info to get.
    default: default value, only valid when it is not None.

  Returns:
    The device info value got.
  """
  if default is not None:
    return GetContext().device_info.get(key, default)
  else:
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


@RuleFunction([])
def GetPhase():
  """A wrapper method to get build phase.

  Returns:
    One of the build phases: PROTO, EVT, DVT, PVT_DOGFOOD, as specified in the
    phase module.
  """
  return str(phase.GetPhase())
