# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""YAML tags used in the HWID database."""

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.test.l10n import regions
from cros.factory.utils import yaml_utils

# Because PyYaml can only represent scalar, sequence, mapping object, the
# customized output format must be one of this:
#   !custom_scalar_tag STRING
#   !custom_sequence_tag [object1, object2]
#   !custom_mapping_tag {key1: value1, key2: value2}
# We cannot only output the tag without any data, such as !region_component.
# Therefore we add a dummy string afterward, and remove it in post-processing.
YAML_DUMMY_STRING = 'YAML_DUMMY_STRING'


def RemoveDummyString(string):
  """Remove the dummy string in the yaml result."""
  return string.replace(" '%s'" % YAML_DUMMY_STRING, '')


class YamlNode(object):
  """This class is for creating RegionField in code.

  We can create RegionField object in two ways. One is parsing from Yaml.
    obj = yaml.load('!RegionField [us, tw]')
  Another one is creating in code with help of this class.
    obj = RegionField([YamlNode('us'), YamlNode('tw')])
  """
  def __init__(self, value=None):
    self.value = value


# pylint: disable=abstract-method
class HWIDV3YAMLTagHandler(yaml_utils.BaseYAMLTagHandler):
  LOADER = yaml.Loader
  DUMPER = yaml.Dumper


class RegionField(dict):
  """A class for holding the region field data in a HWID database."""

  def __init__(self, list_node=None):
    if not isinstance(list_node, list):
      self._is_legacy_style = True
      list_codes = [code for code in regions.LEGACY_REGIONS_LIST
                    if code in regions.REGIONS]

    else:
      self._is_legacy_style = False
      list_codes = [regions.REGIONS[node.value].region_code
                    for node in list_node]

    # The numeric ids of valid regions start from 1.
    # crbug.com/624257: If no explicit regions defined, populate with only the
    # legacy list.
    fields_dict = dict(
        (i + 1, {'region': code}) for i, code in enumerate(list_codes))

    # 0 is a reserved field and is set to {region: []}, so that previous HWIDs
    # which do not have region encoded will not return a bogus region component
    # when being decoded.
    fields_dict[0] = {'region': []}

    super(RegionField, self).__init__(fields_dict)

  @classmethod
  def RebuildRegionField(cls, region_field_data):
    """Gets a `RegionField` object represents for given `region_field` data.

    This function looks if the given data is in legacy style and returns
    corresponding RegionField object.

    Args:
      region_field_data: The given region_field data, should be a dict which
          maps encode index number to a region component.

    Returns:
      An instance of `RegionField`.
    """
    fields_dict = dict(
        (i + 1, {'region': code})
        for i, code in enumerate(regions.LEGACY_REGIONS_LIST)
        if code in regions.REGIONS)
    fields_dict[0] = {'region': []}

    if region_field_data == fields_dict:
      return cls()

    else:
      return cls([YamlNode(region_field_data[index]['region'])
                  for index in xrange(1, max(region_field_data.keys()) + 1)])

  @property
  def is_legacy_style(self):
    return self._is_legacy_style

  def GetRegions(self):
    return [value['region'] for value in self.values() if value['region']]

  def AddRegion(self, new_region):
    if self.is_legacy_style:
      raise ValueError('RegionField with legacy style cannot add new region')
    if new_region not in self.GetRegions():
      idx = max(self.keys()) + 1
      self[idx] = {'region': new_region}


class RegionFieldYAMLTagHandler(HWIDV3YAMLTagHandler):
  """Metaclass for registering the !region_field YAML tag.

  The yaml format of RegionField should be:
    !region_field [<region_code_1>, <region_code_2>,...]
  """
  YAML_TAG = '!region_field'
  TARGET_CLASS = RegionField

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    return cls.TARGET_CLASS(node.value)

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    """Represent the list style of RegionField.

    When the RegionField is legacy style, we output:
        !region_field 'YAML_DUMMY_STRING'
    Otherwise when we dump the RegionField to yaml, it should output like:
        !region_field [us, gb]
    """
    if data.is_legacy_style:
      return dumper.represent_scalar(cls.YAML_TAG, YAML_DUMMY_STRING)

    # 0 is a reserved field for {region: None}. Ignore it.
    region_list = [node['region'] for node in data.values()[1:]]
    return dumper.represent_sequence(cls.YAML_TAG, region_list)


class RegionComponent(dict):
  """A class for holding the region component data in a HWID database."""

  def __init__(self):
    components_dict = {
        'items': {}
    }
    for code, region in regions.REGIONS.iteritems():
      components_dict['items'][code] = {
          'values': {
              'region_code': region.region_code
          }}
    super(RegionComponent, self).__init__(components_dict)


class RegionComponentYAMLTagHandler(HWIDV3YAMLTagHandler):
  """Metaclass for registering the !region_component YAML tag."""
  YAML_TAG = '!region_component'
  TARGET_CLASS = RegionComponent

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    return cls.TARGET_CLASS()

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    return dumper.represent_scalar(cls.YAML_TAG, YAML_DUMMY_STRING)
