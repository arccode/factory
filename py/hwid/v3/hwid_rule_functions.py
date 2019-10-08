# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID specific rule function implementations."""

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3 import hwid_utils
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
def ComponentEq(comp_cls, comp_names):
  """Tests if the components recorded in the BOM object equals to the given
  list of components.

  Args:
    comp_cls: The class name of the component to test.
    comp_names: A list of name of the expected components.

  Returns:
    True if the components of `comp_cls` recorded in the BOM object are exactly
        same as `comp_names`.
  """
  bom = GetContext().bom

  if comp_cls not in bom.components:
    raise HWIDException('The given component class %r is invalid.' % comp_cls)

  return bom.components[comp_cls] == sorted(type_utils.MakeList(comp_names))


@RuleFunction(['bom', 'database'])
def ComponentIn(comp_cls, values):
  """Tests if the components recorded in the BOM object meet the expectation.

  Args:
    comp_cls: The class name of the component to test.
    values: A list of string value or rule.Value for matching the component
        name.

  Returns:
    True if all the components of `comp_cls` recorded in the BOM object match
        at least one of the value in `values`.
  """
  bom = GetContext().bom

  if comp_cls not in bom.components:
    raise HWIDException('The given component class %r is invalid.' % comp_cls)

  values = [Value(value) if not isinstance(value, Value) else value
            for value in type_utils.MakeList(values)]

  return all(any(value.Matches(comp_name) for value in values)
             for comp_name in bom.components[comp_cls])


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
def SetImageId(image_id_name):
  """A function to set the image id of the given HWID context.

  Args:
    image_id_name: The image id or image name to set.
  """
  context = GetContext()
  if isinstance(image_id_name, str):
    # Convert image_id_name string to its corresponding encoded value.
    image_id = context.database.GetImageIdByName(image_id_name)
  else:
    image_id = image_id_name

  if image_id not in context.database.image_ids:
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
  return GetContext().device_info[key]


@RuleFunction([])
def GetBrandCode():
  """A wrapper method to get the DUT's brand code.

  Returns:
    The brand code in lowercase.
  """
  return hwid_utils.ProbeBrandCode()


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
