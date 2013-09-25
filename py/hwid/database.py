# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Database classes for HWID v3 operation."""

import collections
import copy
import pprint
import re
import yaml

import factory_common # pylint: disable=W0611
from cros.factory import rule, schema
from cros.factory.common import MakeList, MakeSet
from cros.factory.hwid import common
from cros.factory.hwid.base32 import Base32
from cros.factory.hwid.base8192 import Base8192


class Database(object):
  """A class for reading in, parsing, and obtaining information of the given
  device-specific component database.

  Attributes:
    board: A string indicating the board name.
    encoding_patterns: An EncodingPatterns object.
    image_id: An ImageId object.
    pattern: A Pattern object.
    encoded_fields: An EncodedFields object.
    components: A Components object.
    rules: A Rules object.
  """
  _HWID_FORMAT = {
      common.HWID.ENCODING_SCHEME.base32: re.compile(
          r'^([A-Z0-9]+)'                 # group(0): Board
          r' ('                           # group(1): Entire BOM.
          r'(?:[A-Z2-7]{4}-)*'            # Zero or more 4-character groups with
                                          # dash.
          r'[A-Z2-7]{1,4}'                # Last group with 1 to 4 characters.
          r')$'                           # End group(1)
      ),
      common.HWID.ENCODING_SCHEME.base8192: re.compile(
          r'^([A-Z0-9]+)'                 # group(0): Board
          r' ('                           # group(1): Entire BOM
          r'(?:[A-Z2-7][2-9][A-Z2-7]-)*'  # Zero or more 3-character groups with
                                          # dash.
          r'[A-Z2-7][2-9][A-Z2-7]'        # Last group with 3 characters.
          r')$'                           # End group(1)
      )}

  def __init__(self, board, encoding_patterns, image_id, pattern,
               encoded_fields, components, rules):
    self.board = board
    self.encoding_patterns = encoding_patterns
    self.image_id = image_id
    self.pattern = pattern
    self.encoded_fields = encoded_fields
    self.components = components
    self.rules = rules
    self._SanityChecks()

  def _SanityChecks(self):
    def _VerifyComponent(comp_cls, comp_name, label):
      try:
        self.components.CheckComponent(comp_cls, comp_name)
      except common.HWIDException as e:
        raise common.HWIDException(
            '%s in %s[%r]' %
            (str(e), label, comp_cls))

    # Check that all the component class-name pairs in encoded_fields are valid.
    for field, indexed_data in self.encoded_fields.iteritems():
      for index, class_name_dict in indexed_data.iteritems():
        for comp_cls, comp_names in class_name_dict.iteritems():
          if comp_names is None:
            _VerifyComponent(comp_cls, None,
                             'encoded_fields[%r][%r]' % (field, index))
            continue
          for comp_name in comp_names:
            _VerifyComponent(comp_cls, comp_name,
                             'encoded_fields[%r][%r]' % (field, index))


  @classmethod
  def LoadFile(cls, file_name):
    """Loads a device-specific component database from the given file and
    parses it to a Database object.

    Args:
      file_name: A path to a device-specific component database.

    Returns:
      A Database object containing all the settings in the database file.

    Raises:
      HWIDException if there is missing field in the database.
    """
    db_yaml = None
    with open(file_name, 'r') as f:
      db_yaml = yaml.load(f)

    return cls.LoadData(db_yaml)

  @classmethod
  def LoadData(cls, db_yaml):
    """Loads a device-specific component database from the given database data.

    Args:
      db_yaml: The database in parsed dict form.

    Returns:
      A Database object containing all the settings in the database file.

    Raises:
      HWIDException if there is missing field in the database.
    """
    if not db_yaml:
      raise common.HWIDException('Invalid HWID database')
    for key in ['board', 'encoding_patterns', 'image_id', 'pattern',
                'encoded_fields', 'components', 'rules']:
      if not db_yaml.get(key):
        raise common.HWIDException(
            '%r is not specified in component database' % key)

    return Database(db_yaml['board'],
                    EncodingPatterns(db_yaml['encoding_patterns']),
                    ImageId(db_yaml['image_id']),
                    Pattern(db_yaml['pattern']),
                    EncodedFields(db_yaml['encoded_fields']),
                    Components(db_yaml['components']),
                    Rules(db_yaml['rules']))

  def ProbeResultToBOM(self, probe_result):
    """Parses the given probe result into a BOM object. Each component is
    represented by its corresponding encoded index in the database.

    Args:
      probe_result: A YAML string of the probe result, which is usually the
          output of the probe command.

    Returns:
      A BOM object.
    """
    probed_bom = yaml.load(probe_result)

    # encoding_pattern_index and image_id are unprobeable and should be set
    # explictly. Defaults them to 0.
    encoding_pattern_index = 0
    image_id = 0

    def LookupProbedValue(comp_cls):
      for field in ['found_probe_value_map', 'found_volatile_values',
                    'initial_configs']:
        if comp_cls in probed_bom[field]:
          # We actually want to return a list of dict here.
          return MakeList(probed_bom[field][comp_cls] if
                          isinstance(probed_bom[field][comp_cls], list) else
                          [probed_bom[field][comp_cls]])
      # comp_cls is in probed_bom['missing_component_classes'].
      return None

    # Construct a dict of component classes to list of ProbedComponentResult.
    probed_components = collections.defaultdict(list)
    for comp_cls in self.components.GetRequiredComponents():
      probed_comp_values = LookupProbedValue(comp_cls)
      if probed_comp_values is not None:
        for probed_value in probed_comp_values:
          if comp_cls not in self.components.probeable:
            probed_components[comp_cls].append(
                common.ProbedComponentResult(
                    None, probed_value,
                    common.UNPROBEABLE_COMPONENT_ERROR(comp_cls)))
            continue
          matched_comps = self.components.MatchComponentsFromValues(
              comp_cls, probed_value)
          if matched_comps is None:
            probed_components[comp_cls].append(common.ProbedComponentResult(
                None, probed_value,
                common.INVALID_COMPONENT_ERROR(comp_cls, probed_value)))
          elif len(matched_comps) == 1:
            comp_name, comp_data = matched_comps.items()[0]
            comp_status = self.components.GetComponentStatus(
                comp_cls, comp_name)
            if comp_status == common.HWID.COMPONENT_STATUS.supported:
              probed_components[comp_cls].append(
                  common.ProbedComponentResult(
                      comp_name, comp_data['values'], None))
            else:
              probed_components[comp_cls].append(
                  common.ProbedComponentResult(
                      comp_name, comp_data['values'],
                      common.UNSUPPORTED_COMPONENT_ERROR(comp_cls, comp_name,
                                                         comp_status)))
          elif len(matched_comps) > 1:
            probed_components[comp_cls].append(common.ProbedComponentResult(
                None, probed_value,
                common.AMBIGUOUS_COMPONENT_ERROR(
                    comp_cls, probed_value, matched_comps)))
      else:
        # No component of comp_cls is found in probe results.
        probed_components[comp_cls].append(common.ProbedComponentResult(
            None, probed_comp_values, common.MISSING_COMPONENT_ERROR(comp_cls)))

    # Encode the components to a dict of encoded fields to encoded indices.
    encoded_fields = {}
    for field in self.encoded_fields:
      encoded_fields[field] = self._GetFieldIndexFromProbedComponents(
          field, probed_components)

    return common.BOM(self.board, encoding_pattern_index, image_id,
                      probed_components, encoded_fields)

  def UpdateComponentsOfBOM(self, bom, updated_components):
    """Updates the components data of the given BOM.

    The components field of the given BOM is updated with the given component
    class and component name, and the encoded_fields field is re-calculated.

    Args:
      bom: A BOM object to update.
      updated_components: A dict of component classes to component names
          indicating the set of components to update.

    Returns:
      A BOM object with updated components and encoded fields.
    """
    result = bom.Duplicate()
    for comp_cls, comp_name in updated_components.iteritems():
      new_probed_result = []
      if comp_name is None:
        new_probed_result.append(common.ProbedComponentResult(
            None, None, common.MISSING_COMPONENT_ERROR(comp_cls)))
      else:
        comp_name = MakeList(comp_name)
        for name in comp_name:
          comp_attrs = self.components.GetComponentAttributes(comp_cls, name)
          new_probed_result.append(common.ProbedComponentResult(
              name, comp_attrs['values'], None))
      # Update components data of the duplicated BOM.
      result.components[comp_cls] = new_probed_result

    # Re-calculate all the encoded index of each encoded field.
    result.encoded_fields = {}
    for field in self.encoded_fields:
      result.encoded_fields[field] = self._GetFieldIndexFromProbedComponents(
          field, result.components)

    return result

  def _GetFieldIndexFromProbedComponents(self, encoded_field,
                                         probed_components):
    """Gets the encoded index of the specified encoded field by matching
    the given probed components against the definitions in the database.

    Args:
      encoded_field: A string indicating the encoding field of interest.
      probed_components: A dict that maps a set of component classes to their
          list of ProbedComponentResult.

    Returns:
      An int indicating the encoded index, or None if no matching encoded
      index is found.
    """
    if encoded_field not in self.encoded_fields:
      return None

    for index, db_comp_cls_names in (
        self.encoded_fields[encoded_field].iteritems()):
      # Iterate through all indices in the encoded_fields of the database.
      found = True
      for db_comp_cls, db_comp_names in db_comp_cls_names.iteritems():
        # Check if every component class and value the index consists of
        # matches.
        if db_comp_names is None:
          # Special handling for NULL component.
          if (probed_components[db_comp_cls] and
              probed_components[db_comp_cls][0].probed_values is not None):
            found = False
            break
        else:
          # Create a set of component names of db_comp_cls from the
          # probed_components argument.
          bom_component_names_of_the_class = MakeSet([
              x.component_name for x in probed_components[db_comp_cls]])
          # Create a set of component names of db_comp_cls from the database.
          db_component_names_of_the_class = MakeSet(db_comp_names)
          if (bom_component_names_of_the_class !=
              db_component_names_of_the_class):
            found = False
            break
      if found:
        return index
    return None

  def _GetAllIndices(self, encoded_field):
    """Gets a list of all the encoded indices of the given encoded_field in the
    database.

    Args:
      encoded_field: The encoded field of interest.

    Return:
      A list of ints of the encoded indices.
    """
    return [key for key in self.encoded_fields[encoded_field]
            if isinstance(key, int)]

  def _GetAttributesByIndex(self, encoded_field, index):
    """Gets the attributes of all the component(s) of a encoded field through
    the given encoded index.

    Args:
      encoded_field: The encoded field of interest.
      index: The index of the component.

    Returns:
      A dict indexed by component classes that includes a list of all the
      attributes of the components represented by the encoded index, or None if
      the index if not found.
    """
    if encoded_field not in self.encoded_fields:
      return None
    if index not in self.encoded_fields[encoded_field]:
      return None
    result = collections.defaultdict(list)
    for comp_cls, comp_names in (
        self.encoded_fields[encoded_field][index].iteritems()):
      if comp_names is None:
        result[comp_cls] = None
      else:
        for name in comp_names:
          # Add an additional index 'name' to record component name
          new_attr = self.components.GetComponentAttributes(comp_cls, name)
          new_attr['name'] = name
          result[comp_cls].append(new_attr)
    return result

  def VerifyBinaryString(self, binary_string):
    """Verifies the binary string.

    Raises:
      HWIDException if verification fails.
    """
    if set(binary_string) - set('01'):
      raise common.HWIDException('Invalid binary string: %r' % binary_string)

    if '1' not in binary_string:
      raise common.HWIDException('Binary string %r does not have stop bit set',
                          binary_string)
    # Truncate trailing 0s.
    string_without_paddings = binary_string[:binary_string.rfind('1') + 1]

    image_id = self.pattern.GetImageIdFromBinaryString(binary_string)
    if len(string_without_paddings) > self.pattern.GetTotalBitLength(image_id):
      raise common.HWIDException('Invalid bit string length of %r. Expected '
                          'length <= %d, got length %d' %
                          (binary_string,
                           self.pattern.GetTotalBitLength(image_id),
                           len(string_without_paddings)))

  def VerifyEncodedString(self, encoded_string):
    """Verifies the given encoded string.

    Raises:
      HWIDException if verification fails.
    """
    try:
      image_id = self.pattern.GetImageIdFromEncodedString(encoded_string)
      encoding_scheme = self.pattern.GetPatternByImageId(
        image_id)['encoding_scheme']
      board, bom_checksum = Database._HWID_FORMAT[encoding_scheme].findall(
          encoded_string)[0]
    except IndexError:
      raise common.HWIDException(
          'Invalid HWID string format: %r' % encoded_string)
    if len(bom_checksum) < 2:
      raise common.HWIDException(
          'Length of encoded string %r is less than 2 characters' %
          bom_checksum)
    if not board == self.board.upper():
      raise common.HWIDException('Invalid board name: %r' % board)
    # Verify the checksum
    stripped = encoded_string.replace('-', '')
    hwid = stripped[:-2]
    checksum = stripped[-2:]
    if encoding_scheme == common.HWID.ENCODING_SCHEME.base32:
      expected_checksum = Base32.Checksum(hwid)
    elif encoding_scheme == common.HWID.ENCODING_SCHEME.base8192:
      expected_checksum = Base8192.Checksum(hwid)
    if not checksum == expected_checksum:
      raise common.HWIDException('Checksum of %r mismatch (expected %r)' % (
          encoded_string, expected_checksum))

  def VerifyBOM(self, bom):
    """Verifies the data contained in the given BOM object matches the settings
    and definitions in the database.

    Raises:
      HWIDException if verification fails.
    """
    # All the classes encoded in the pattern should exist in BOM.
    missing_comp = []
    for encoded_indices in self.encoded_fields.itervalues():
      for index_content in encoded_indices.itervalues():
        missing_comp.extend([comp_cls for comp_cls in index_content
                             if comp_cls not in bom.components])
    if missing_comp:
      raise common.HWIDException('Missing component classes: %r',
                          ', '.join(sorted(missing_comp)))

    bom_encoded_fields = MakeSet(bom.encoded_fields.keys())
    db_encoded_fields = MakeSet(self.encoded_fields.keys())
    # Every encoded field defined in the database must present in BOM.
    if db_encoded_fields - bom_encoded_fields:
      raise common.HWIDException('Missing encoded fields in BOM: %r',
                          ', '.join(sorted(db_encoded_fields -
                                           bom_encoded_fields)))
    # Every encoded field the BOM has must exist in the database.
    if bom_encoded_fields - db_encoded_fields:
      raise common.HWIDException('Extra encoded fields in BOM: %r',
                          ', '.join(sorted(bom_encoded_fields -
                                           db_encoded_fields)))

    if bom.board != self.board:
      raise common.HWIDException('Invalid board name. Expected %r, got %r' %
                          (self.board, bom.board))

    if bom.encoding_pattern_index not in self.encoding_patterns:
      raise common.HWIDException('Invalid encoding pattern: %r' %
                          bom.encoding_pattern_index)
    if bom.image_id not in self.image_id:
      raise common.HWIDException('Invalid image id: %r' % bom.image_id)

    # All the probeable component values in the BOM should exist in the
    # database.
    unknown_values = []
    for comp_cls, probed_values in bom.components.iteritems():
      for element in probed_values:
        probed_values = element.probed_values
        if probed_values is None or comp_cls not in self.components.probeable:
          continue
        found_comps = (
            self.components.MatchComponentsFromValues(comp_cls, probed_values))
        if not found_comps:
          unknown_values.append('%s:%s' % (comp_cls, pprint.pformat(
              probed_values, indent=0, width=1024)))
    if unknown_values:
      raise common.HWIDException('Unknown component values: %r' %
                          ', '.join(sorted(unknown_values)))

    # All the encoded index should exist in the database.
    invalid_fields = []
    for field, index in bom.encoded_fields.iteritems():
      if index is not None and index not in self.encoded_fields[field]:
        invalid_fields.append(field)
    if invalid_fields:
      raise common.HWIDException('Encoded fields %r have unknown indices' %
                          ', '.join(sorted(invalid_fields)))

  def VerifyComponents(self, probe_result, comp_list=None):
    """Given a list of component classes, verify that the probed components of
    all the component classes in the list are valid components in the database.

    Args:
      probe_result: A YAML string of the probe result, which is usually the
          output of the probe command.
      comp_list: An optional list of component class to be verified. Defaults to
          None, which will then verify all the probeable components defined in
          the database.

    Returns:
      A dict from component class to a list of one or more
      ProbedComponentResult tuples.
      {component class: [ProbedComponentResult(
          component_name,  # The component name if found in the db, else None.
          probed_values,   # The actual probed string. None if probing failed.
          error)]}         # The error message if there is one; else None.
    """
    probed_bom = self.ProbeResultToBOM(probe_result)
    if not comp_list:
      comp_list = sorted(self.components.probeable)
    if not isinstance(comp_list, list):
      raise common.HWIDException('Argument comp_list should be a list')
    invalid_cls = set(comp_list) - set(self.components.probeable)
    if invalid_cls:
      raise common.HWIDException(
          '%r do not have probe values and cannot be verified' %
          sorted(invalid_cls))
    return dict((comp_cls, probed_bom.components[comp_cls]) for comp_cls in
                comp_list)


class EncodingPatterns(dict):
  """Class for parsing encoding_patterns in database.

  Args:
    encoding_patterns_dict: A dict of encoding patterns of the form:
        {
          0: 'default',
          1: 'extra_encoding_pattern',
          ...
        }
  """
  def __init__(self, encoding_patterns_dict):
    self.schema = schema.Dict('encoding patterns',
                       key_type=schema.Scalar('encoding pattern', int),
                       value_type=schema.Scalar('encoding scheme', str))
    self.schema.Validate(encoding_patterns_dict)
    super(EncodingPatterns, self).__init__(encoding_patterns_dict)


class ImageId(dict):
  """Class for parsing image_id in database.

  Args:
    image_id_dict: A dict of image ids of the form:
        {
          0: 'image_id0',
          1: 'image_id1',
          ...
        }
  """
  def __init__(self, image_id_dict):
    self.schema = schema.Dict('image id',
                       key_type=schema.Scalar('image id', int),
                       value_type=schema.Scalar('image name', str))
    self.schema.Validate(image_id_dict)
    super(ImageId, self).__init__(image_id_dict)


class EncodedFields(dict):
  """Class for parsing encoded_fields in database.

  Args:
    encoded_fields_dict: A dict of encoded fields of the form:
        {
          'encoded_field_name1': {
            0: {
              'component_class1': 'component_name1',
              'component_class2': ['component_name2', 'component_name3']
              ...
            }
            1: {
              'component_class1': 'component_name4',
              'component_class2': None,
              ...
            }
          }
          'encoded_field_name2':
          ...
        }
  """
  def __init__(self, encoded_fields_dict):
    self.schema = schema.Dict(
      'encoded fields', schema.Scalar('encoded field', str),
      schema.Dict(
          'encoded indices', schema.Scalar('encoded index', int),
          schema.Dict(
              'component classes', schema.Scalar('component class', str),
              schema.Optional([schema.Scalar('component name', str),
                               schema.List('list of component names',
                               schema.Scalar('component name', str))]))))
    self.schema.Validate(encoded_fields_dict)
    super(EncodedFields, self).__init__(encoded_fields_dict)
    # Convert string to list of string.
    for field in self:
      for index in self[field]:
        for comp_cls in self[field][index]:
          comp_value = self[field][index][comp_cls]
          if isinstance(comp_value, str):
            self[field][index][comp_cls] = MakeList(comp_value)


class Components(object):
  """A class for parsing and obtaining information of a pre-defined components
  list.

  Args:
    components_dict: A dict of components of the form:
        {
          'component_class_1': {      # Probeable component class.
            'probeable': True,
            'items': {
              'component_name_1': {
                'values': { probed values dict },
                'labels': [ labels ],
                'status': status
              },
              ...
            }
          },
          'component_class_2': {      # Unprobeable component class.
            'probeable': False,
            'items': {
              'component_name_2': {
                'values': None,
                'labels': [ labels ],
                'status': status
              },
              ...
            }
          },
          ...
        }

  Raises:
    HWIDException if the given dict fails sanity checks.
  """
  def __init__(self, components_dict):
    self.schema = schema.Dict(
        'components',
        schema.Scalar('component class', str),
        schema.FixedDict(
            'component description',
            items={
                'items': schema.Dict(
                    'component names',
                    key_type=schema.Scalar('component name', str),
                    value_type=schema.FixedDict(
                        'component attributes',
                        items={'values': schema.Optional(
                            schema.Dict('probe key-value pairs',
                                 key_type=schema.Scalar('probe key', str),
                                 value_type=schema.AnyOf([
                                     schema.Scalar('probe value', str),
                                     schema.Scalar('probe value regexp',
                                                   rule.Value)])))},
                        optional_items={
                            'labels': schema.Dict(
                                'dict of labels',
                                key_type=schema.Scalar('label key', str),
                                value_type=schema.Scalar('label value', str)),
                            'status': schema.Scalar('item status', str)}))
            },
            optional_items={
                'probeable': schema.Scalar('is component probeable', bool)
            }))
    self.schema.Validate(components_dict)

    # Classify components based on their attributes.
    self.probeable = set()
    for comp_cls, comp_cls_properties in components_dict.iteritems():
      if comp_cls_properties.get('probeable', True):
        # Default 'probeable' to True.
        self.probeable.add(comp_cls)

    for comp_cls_data in components_dict.itervalues():
      for comp_cls_item_attrs in comp_cls_data['items'].itervalues():
        # Sanity check for component status.
        status = comp_cls_item_attrs.get(
            'status', common.HWID.COMPONENT_STATUS.supported)
        if status not in common.HWID.COMPONENT_STATUS:
          raise common.HWIDException(
              'Invalid component item status: %r' % status)

        # Convert all probe values to Value objects.
        if comp_cls_item_attrs['values'] is None:
          continue
        for key, value in comp_cls_item_attrs['values'].items():
          if not isinstance(value, rule.Value):
            comp_cls_item_attrs['values'][key] = rule.Value(value)

    self.components_dict = components_dict

  def GetRequiredComponents(self):
    """Gets the list of required component classes.

    Returns:
      A set of component classes that are required to present on board.
    """
    return set(self.components_dict.keys())

  def GetComponentAttributes(self, comp_cls, comp_name):
    """Gets the attributes of the given component.

    Args:
      comp_cls: The component class to look up for.
      comp_name: The component name to look up for.

    Returns:
      A copy of the dict that contains all the attributes of the given
      component.
    """
    self.CheckComponent(comp_cls, comp_name)
    if not comp_name:
      # Missing component.
      return {}
    return copy.deepcopy(self.components_dict[comp_cls]['items'][comp_name])

  def GetComponentStatus(self, comp_cls, comp_name):
    """Gets the status of the given component.

    Args:
      comp_cls: The component class to look up for.
      comp_name: The component name to look up for.

    Returns:
      One of the status in Components.STATUS indicating the status of the given
      component.
    """
    return self.components_dict[comp_cls]['items'][comp_name].get(
        'status', common.HWID.COMPONENT_STATUS.supported)

  def MatchComponentsFromValues(self, comp_cls, values_dict):
    """Matches a list of components whose 'values' attributes match the given
    'values_dict'.

    Only the fields listed in the 'values' dict of each component are used as
    matching keys.

    For example, this may be used to look up all the dram components that are of
    size 4G with {'size': '4G'} as 'values_dict' and 'dram' as 'comp_cls'.

    Args:
      comp_cls: The component class of interest.
      values_dict: A dict of values to be used as look up key.

    Returns:
      A dict with keys being the matched component names and values being the
      dict of component attributes corresponding to the component names.

    Raises:
      HWIDException if the given component class is invalid.
    """
    self.CheckComponent(comp_cls, None)
    results = {}
    for comp_name, comp_attrs in (
        self.components_dict[comp_cls]['items'].iteritems()):
      if comp_attrs['values'] is None and values_dict is None:
        # Special handling for None values.
        results[comp_name] = copy.deepcopy(comp_attrs)
      elif comp_attrs['values'] is None:
        continue
      else:
        match = True
        for key, value in comp_attrs['values'].iteritems():
          # Only match the listed fields in 'values'.
          if key not in values_dict or not value.Matches(values_dict[key]):
            match = False
            break
        if match:
          results[comp_name] = copy.deepcopy(comp_attrs)
    if results:
      return results
    return None

  def CheckComponent(self, comp_cls, comp_name):
    """Checks if the given component class and component name are valid.

    Args:
      comp_cls: The component class to check.
      comp_name: The component name to check. Set this to None will check
          component class validity only.

    Raises:
      HWIDException if the given component class or name are invalid.
    """
    if comp_cls not in self.components_dict:
      raise common.HWIDException('Invalid component class %r' % comp_cls)
    if comp_name and comp_name not in self.components_dict[comp_cls]['items']:
      raise common.HWIDException(
          'Invalid component name %r of class %r' % (comp_name, comp_cls))


class Pattern(object):
  """A class for parsing and obtaining information of a pre-defined encoding
  pattern.

  Args:
    pattern_list: A list of dicts that maps encoded fields to their
        bit length.
  """
  def __init__(self, pattern_list):
    self.schema = schema.List(
        'pattern', schema.FixedDict(
            'pattern list', items={
                'image_ids': schema.List('image ids', schema.Scalar('image id',
                                                                    int)),
                'encoding_scheme': schema.Scalar('encoding scheme', str),
                'fields': schema.List('encoded fields', schema.Dict(
                    'pattern field', key_type=schema.Scalar(
                        'encoded index', str),
                    value_type=schema.Scalar('bit offset', int)))}))
    self.schema.Validate(pattern_list)
    self.pattern = pattern_list

  def GetPatternByImageId(self, image_id=None):
    """Get pattern definition by image id.

    Args:
      image_id: An integer of the image id to query. If not given, the latest
          image id would be used.

    Returns:
      A dict of the pattern definiton.
    """
    id_pattern_map = {}
    for pattern in self.pattern:
      id_pattern_map.update(dict((image_id, pattern) for image_id in
                                 pattern['image_ids']))
    if image_id is None:
      return id_pattern_map[max(id_pattern_map.keys())]

    if image_id not in id_pattern_map:
      raise common.HWIDException(
          'Pattern for image id %r is not defined' % image_id)

    return id_pattern_map[image_id]

  def GetImageIdFromEncodedString(self, encoded_string):
    return int(Base32.Decode(encoded_string.split(' ')[1][0])[1:5], 2)

  def GetImageIdFromBinaryString(self, binary_string):
    return int(binary_string[1:5], 2)

  def GetFieldsBitLength(self, image_id=None):
    """Gets a map for the bit length of each encoded fields defined by the
    pattern. Scattered fields with the same field name are aggregated into one.

    Returns:
      A dict mapping each encoded field to its bit length.
    """
    if self.pattern is None:
      raise common.HWIDException(
          'Cannot get encoded field bit length with uninitialized pattern')
    ret = collections.defaultdict(int)
    for element in self.GetPatternByImageId(image_id)['fields']:
      for cls, length in element.iteritems():
        ret[cls] += length
    return ret

  def GetTotalBitLength(self, image_id=None):
    """Gets the total bit length defined by the pattern. Common header and
    stopper bit are included.

    Returns:
      A int indicating the total bit length.
    """
    if self.pattern is None:
      raise common.HWIDException(
          'Cannot get bit length with uninitialized pattern')
    # 5 bits for header and 1 bit for stop bit
    return (common.HWID.HEADER_BITS + 1 +
            sum(self.GetFieldsBitLength(image_id).values()))

  def GetBitMapping(self, image_id=None):
    """Gets a map indicating the bit offset of certain encoded field a bit in a
    encoded binary string corresponds to.

    For example, the returned map may say that bit 5 in the encoded binary
    string corresponds to the least significant bit of encoded field 'cpu'.

    Returns:
      A list of BitEntry objects indexed by bit position in the encoded binary
      string. Each BitEntry object has attributes (field, bit_offset) indicating
      which bit_offset of field this particular bit corresponds to. For example,
      if ret[6] has attributes (field='cpu', bit_offset=1), then it means that
      bit position 6 of the encoded binary string corresponds to the bit offset
      1 (which is the second least significant bit) of encoded field 'cpu'.
    """
    BitEntry = collections.namedtuple('BitEntry', ['field', 'bit_offset'])

    if self.pattern is None:
      raise common.HWIDException(
          'Cannot construct bit mapping with uninitialized pattern')
    ret = {}
    index = common.HWID.HEADER_BITS   # Skips the 5-bit common header.
    field_offset_map = collections.defaultdict(int)
    for element in self.GetPatternByImageId(image_id)['fields']:
      for field, length in element.iteritems():
        # Reverse bit order.
        field_offset_map[field] += length
        first_bit_index = field_offset_map[field] - 1
        for field_index in xrange(
            first_bit_index, first_bit_index - length, -1):
          ret[index] = BitEntry(field, field_index)
          index += 1
    return ret

  def GetBitMappingSpringEVT(self, image_id=None):
    """Gets a map indicating the bit offset of certain encoded field a bit in a
    encoded binary string corresponds to.

    This is a hack for Spring EVT, which used the LSB first encoding pattern.

    Returns:
      A list of BitEntry objects indexed by bit position in the encoded binary
      string. Each BitEntry object has attributes (field, bit_offset) indicating
      which bit_offset of field this particular bit corresponds to. For example,
      if ret[6] has attributes (field='cpu', bit_offset=1), then it means that
      bit position 6 of the encoded binary string corresponds to the bit offset
      1 (which is the second least significant bit) of encoded field 'cpu'.
    """
    BitEntry = collections.namedtuple('BitEntry', ['field', 'bit_offset'])

    if self.pattern is None:
      raise common.HWIDException(
          'Cannot construct bit mapping with uninitialized pattern')
    ret = {}
    index = common.HWID.HEADER_BITS   # Skips the 5-bit common header.
    field_offset_map = collections.defaultdict(int)
    for element in self.GetPatternByImageId(image_id)['fields']:
      for field, length in element.iteritems():
        for _ in xrange(length):
          ret[index] = BitEntry(field, field_offset_map[field])
          field_offset_map[field] += 1
          index += 1
    return ret


class Rules(object):
  """A class for parsing and evaluating rules defined in the database.

  Args:
    rule_list: A list of dicts that can be converted to a list of Rule objects.
  """
  def __init__(self, rule_list):
    self.schema = schema.List('list of rules', schema.FixedDict(
        'rule', items={
            'name': schema.Scalar('rule name', str),
            'evaluate': schema.AnyOf([
                schema.Scalar('rule function', str),
                schema.List('list of rule functions',
                            schema.Scalar('rule function', str))])
        }, optional_items={
            'when': schema.Scalar('expression', str),
            'otherwise': schema.AnyOf([
                schema.Scalar('rule function', str),
                schema.List('list of rule functions',
                            schema.Scalar('rule function', str))])
        }))
    self.schema.Validate(rule_list)
    self.initialized = False
    self.rule_list = [rule.Rule.CreateFromDict(r) for r in rule_list]

  def _Initialize(self):
    # Lazy import to avoid circular import problems. This also avoids import
    # when only decoding functions are needed.
    # These imports are needed to make sure all the rule functions needed by
    # HWID-related operations are loaded and initialized.
    # pylint: disable = W0612
    import cros.factory.common_rule_functions
    import cros.factory.hwid.hwid_rule_functions
    self.initialized = True

  def EvaluateRules(self, context, namespace=None):
    """Evaluate rules under the given context. If namespace is specified, only
    those rules with names matching the specified namespace is evaluated.

    Args:
      context: A Context object holding all the context needed to evaluate the
          rules.
      namespace: A regular expression string indicating the rules to be
          evaluated.
    """
    if not self.initialized:
      self._Initialize()
    for r in self.rule_list:
      if namespace is None or re.match(namespace, r.name):
        r.Evaluate(context)
