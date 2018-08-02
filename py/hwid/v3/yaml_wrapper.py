# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A yaml module wrapper for HWID v3.

This module overwrites the functions we are interested in to make a separation
from the origin yaml module.
"""

import collections
import functools

from yaml import *  # pylint: disable=wildcard-import,unused-wildcard-import
from yaml import constructor
from yaml import nodes
from yaml import resolver

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import rule
from cros.factory.test.l10n import regions
from cros.factory.utils import schema
from cros.factory.utils import yaml_utils

class V3Loader(SafeLoader):
  """A HWID v3 yaml Loader for patch separation."""
  pass


class V3Dumper(SafeDumper):
  """A HWID v3 yaml Dumper for patch separation."""
  pass


# Because PyYaml can only represent scalar, sequence, mapping object, the
# customized output format must be one of this:
#   !custom_scalar_tag STRING
#   !custom_sequence_tag [object1, object2]
#   !custom_mapping_tag {key1: value1, key2: value2}
# We cannot only output the tag without any data, such as !region_component.
# Therefore we add a dummy string afterward, and remove it in post-processing.
_YAML_DUMMY_STRING = 'YAML_DUMMY_STRING'


def _RemoveDummyStringWrapper(func):
  def wrapper(*args, **kwargs):
    """Remove the dummy string in the yaml result."""
    return func(*args, **kwargs).replace(" '%s'" % _YAML_DUMMY_STRING, '')
  return wrapper


# Overwrite the globals from the yaml module
Loader = V3Loader
Dumper = V3Dumper

# Patch functions to use V3Loader and V3Dumper
load = functools.partial(load, Loader=Loader)
load_all = functools.partial(load_all, Loader=Loader)
add_constructor = functools.partial(add_constructor, Loader=Loader)
dump = _RemoveDummyStringWrapper(functools.partial(dump, Dumper=Dumper))
dump_all = _RemoveDummyStringWrapper(functools.partial(dump_all, Dumper=Dumper))
add_representer = functools.partial(add_representer, Dumper=Dumper)


# Register customized YAML tags

# pylint: disable=abstract-method
class _HWIDV3YAMLTagHandler(yaml_utils.BaseYAMLTagHandler):
  LOADER = Loader
  DUMPER = Dumper


# The dictionary class for the HWID database object.
Dict = collections.OrderedDict


class _DefaultMappingHandler(_HWIDV3YAMLTagHandler):
  YAML_TAG = resolver.BaseResolver.DEFAULT_MAPPING_TAG
  TARGET_CLASS = Dict

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    if not isinstance(node, nodes.MappingNode):
      raise constructor.ConstructorError(
          None, None, 'expected a mapping node, but found %s' % node.id,
          node.start_mark)
    mapping = cls.TARGET_CLASS()
    for key_node, value_node in node.value:
      key = loader.construct_object(key_node, deep=deep)
      try:
        hash(key)
      except TypeError:
        raise constructor.ConstructorError(
            'while constructing a mapping', node.start_mark,
            'found unacceptable key (%s)' % key, key_node.start_mark)
      value = loader.construct_object(value_node, deep=deep)
      if key in mapping:
        raise constructor.ConstructorError(
            'while constructing a mapping', node.start_mark,
            'found duplicated key (%s)' % key, key_node.start_mark)
      mapping[key] = value
    return mapping

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    return dumper.represent_dict(data.iteritems())


class _RegionField(dict):
  """A class for holding the region field data in a HWID database."""

  def __init__(self, region_names=None):
    if region_names is None:
      self._is_legacy_style = True
      region_names = [code for code in regions.LEGACY_REGIONS_LIST
                      if code in regions.REGIONS]

    else:
      self._is_legacy_style = False

    # The numeric ids of valid regions start from 1.
    # crbug.com/624257: If no explicit regions defined, populate with only the
    # legacy list.
    fields_dict = dict(
        (i + 1, {'region': n}) for i, n in enumerate(region_names))

    # 0 is a reserved field and is set to {region: []}, so that previous HWIDs
    # which do not have region encoded will not return a bogus region component
    # when being decoded.
    fields_dict[0] = {'region': []}

    super(_RegionField, self).__init__(fields_dict)

  @property
  def is_legacy_style(self):
    return self._is_legacy_style


class _RegionFieldYAMLTagHandler(_HWIDV3YAMLTagHandler):
  """Metaclass for registering the !region_field YAML tag.

  The yaml format of RegionField should be:
    !region_field [<region_code_1>, <region_code_2>,...]
  """
  YAML_TAG = '!region_field'
  TARGET_CLASS = _RegionField

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    if isinstance(node, nodes.SequenceNode):
      return cls.TARGET_CLASS(loader.construct_sequence(node, deep=deep))
    else:
      return cls.TARGET_CLASS()

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    """Represent the list style of RegionField.

    When the RegionField is legacy style, we output:
        !region_field 'YAML_DUMMY_STRING'
    Otherwise when we dump the RegionField to yaml, it should output like:
        !region_field [us, gb]
    """
    if data.is_legacy_style:
      return dumper.represent_scalar(cls.YAML_TAG, _YAML_DUMMY_STRING)

    # 0 is a reserved field for {region: None}. Ignore it.
    region_list = [node['region'] for node in data.values()[1:]]
    return dumper.represent_sequence(cls.YAML_TAG, region_list)


class _RegionComponent(dict):
  """A class for holding the region component data in a HWID database.

  The instance of this class is expected to be frozen after constructing.
  """
  def __init__(self, status_lists=None):
    # Load system regions.
    components_dict = {'items': {}}
    for code, region in regions.BuildRegionsDict(include_all=True).iteritems():
      region_comp = {'values': {'region_code': region.region_code}}
      if code not in regions.REGIONS:
        region_comp['status'] = common.COMPONENT_STATUS.unsupported
      components_dict['items'][code] = region_comp

    # Apply customized status lists.
    if status_lists is not None:
      for status in common.COMPONENT_STATUS:
        for region in status_lists.get(status, []):
          components_dict['items'][region]['status'] = status

    super(_RegionComponent, self).__init__(components_dict)
    self.status_lists = status_lists

  def __eq__(self, rhs):
    return (isinstance(rhs, _RegionComponent) and
            super(_RegionComponent, self).__eq__(rhs) and
            self.status_lists == rhs.status_lists)

  def __ne__(self, rhs):
    return not self.__eq__(rhs)


class _RegionComponentYAMLTagHandler(_HWIDV3YAMLTagHandler):
  """Metaclass for registering the !region_component YAML tag."""
  YAML_TAG = '!region_component'
  TARGET_CLASS = _RegionComponent

  _STATUS_LISTS_SCHEMA = schema.FixedDict('status lists', optional_items={
      s: schema.List('regions', element_type=schema.Scalar('region', str),
                     min_length=1)
      for s in common.COMPONENT_STATUS})

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    if isinstance(node, nodes.ScalarNode):
      if node.value:
        raise constructor.ConstructorError(
            'expected empty scalar node, but got %r' % node.value)
      return cls.TARGET_CLASS()
    else:
      status_lists = _DefaultMappingHandler.YAMLConstructor(
          loader, node, deep=True)
      cls._VerifyStatusLists(status_lists)
      return cls.TARGET_CLASS(status_lists)

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    if data.status_lists is None:
      return dumper.represent_scalar(cls.YAML_TAG, _YAML_DUMMY_STRING)
    else:
      return dumper.represent_mapping(cls.YAML_TAG, data.status_lists)

  @classmethod
  def _VerifyStatusLists(cls, status_lists):
    try:
      cls._STATUS_LISTS_SCHEMA.Validate(status_lists)
    except schema.SchemaException as e:
      raise constructor.ConstructorError(str(e) + '%r' % status_lists)

    for i, s1 in enumerate(status_lists.keys()):
      for s2 in status_lists.keys()[i + 1:]:
        duplicated_regions = set(status_lists[s1]) & set(status_lists[s2])
        if duplicated_regions:
          raise constructor.ConstructorError(
              'found ambiguous status for regions %r' % duplicated_regions)


class _RegexpYAMLTagHandler(_HWIDV3YAMLTagHandler):
  """Class for creating regular expression-enabled Value object.

  This class registers YAML constructor and representer to decode from YAML
  tag '!re' and data to a Value object, and to encode a Value object to its
  corresponding YAML representation.
  """
  YAML_TAG = '!re'
  TARGET_CLASS = rule.Value

  @classmethod
  def YAMLConstructor(cls, loader, node, deep=False):
    value = loader.construct_scalar(node)
    return cls.TARGET_CLASS(value, is_re=True)

  @classmethod
  def YAMLRepresenter(cls, dumper, data):
    if data.is_re:
      return dumper.represent_scalar(cls.YAML_TAG, data.raw_value)
    else:
      return dumper.represent_data(data.raw_value)
