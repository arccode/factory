#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common classes for HWID v3 operation."""

import collections
import copy
import logging
import os
import re
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeList, MakeSet
from cros.factory.hwid.base32 import Base32
from cros.factory.schema import AnyOf, Dict, FixedDict, List, Optional
from cros.factory.schema import Scalar, Tuple
from cros.factory.test import utils


# The expected location of HWID data within a factory image or the
# chroot.
DEFAULT_HWID_DATA_PATH = (
    os.path.join(os.environ['CROS_WORKON_SRCROOT'],
                 'src', 'platform', 'chromeos-hwid', 'v3')
    if utils.in_chroot()
    else '/usr/local/factory/hwid')


def ProbeBoard():
  """Probes the board name by looking up the CHROMEOS_RELEASE_BOARD variable
  in /etc/lsb-release.

  Returns:
    The probed board name as a string.

  Raises:
    HWIDException when probe error.
  """
  LSB_RELEASE_FILE = '/etc/lsb-release'
  LSB_BOARD_RE = re.compile(r'^CHROMEOS_RELEASE_BOARD=(\w+)$', re.M)
  if utils.in_chroot():
    raise HWIDException('Unable to determine board in chroot')
  if not os.path.exists(LSB_RELEASE_FILE):
    raise HWIDException('%r does not exist, unable to determine board' %
                        LSB_RELEASE_FILE)
  try:
    with open(LSB_RELEASE_FILE) as f:
      board = LSB_BOARD_RE.findall(f.read())[0].rpartition('_')[-1]
  except IndexError:
    raise HWIDException('Cannot determine board from %r' % LSB_RELEASE_FILE)
  return board


# A named tuple to store the probed component name and the error if any.
ProbedComponentResult = collections.namedtuple(
    'ProbedComponentResult', ['component_name', 'probed_string', 'error'])

class HWIDException(Exception):
  pass


class HWID(object):
  """A class that holds all the context of a HWID.

  It verifies the correctness of the HWID when a new HWID object is created.
  This class is mainly for internal use. User should not create a HWID object
  directly with the constructor.

  With bom (obatined from hardware prober) and board-specific component
  database, HWID encoder can derive binary_string and encoded_string.
  Reversely, with encoded_string and board-specific component database, HWID
  decoder can derive binary_string and bom.

  Attributes:
    database: A board-specific Database object.
    binary_string: A binary string. Ex: "0000010010..." It is used for fast
        component lookups as each component is represented by one or multiple
        bits at fixed positions.
    encoded_string: An encoded string with board name and checksum. For example:
        "CHROMEBOOK ASDF-2345", where CHROMEBOOK is the board name and 45 is the
        checksum. Compare to binary_string, it is human-trackable.
    bom: A BOM object.

  Raises:
    HWIDException if an invalid arg is found.
  """
  HEADER_BITS = 5

  def __init__(self, database, binary_string, encoded_string, bom):
    self.database = database
    self.binary_string = binary_string
    self.encoded_string = encoded_string
    self.bom = bom
    self.VerifySelf()

  def VerifySelf(self):
    """Verifies the HWID object itself.

    Raises:
      HWIDException on verification error.
    """
    # pylint: disable=W0404
    from cros.factory.hwid.encoder import BOMToBinaryString
    from cros.factory.hwid.encoder import BinaryStringToEncodedString
    self.database.VerifyBOM(self.bom)
    self.database.VerifyBinaryString(self.binary_string)
    self.database.VerifyEncodedString(self.encoded_string)
    if (BinaryStringToEncodedString(self.database, self.binary_string) !=
        self.encoded_string):
      raise HWIDException(
          'Binary string %s does not encode to encoded string %r' %
          (self.binary_string, self.encoded_string))
    if BOMToBinaryString(self.database, self.bom) != self.binary_string:
      raise HWIDException('BOM does not encode to binary string %r' %
                          self.binary_string)
    # No exception. Everything is good!

  def VerifyProbeResult(self, probe_result):
    """Verifies that the probe result matches the settings encoded in the HWID
    object.

    Args:
      probe_result: A YAML string of the probe result, which is usually the
          output of the probe command.

    Raises:
      HWIDException on verification error.
    """
    self.database.VerifyComponents(probe_result)
    probed_bom = self.database.ProbeResultToBOM(probe_result)
    def PackProbedString(bom, comp_cls):
      return [e.probed_string for e in bom.components[comp_cls] if
              e.probed_string is not None]
    for comp_cls in self.database.components:
      if comp_cls not in self.database.probeable_components:
        continue
      probed_comp_values = MakeSet(PackProbedString(probed_bom, comp_cls))
      expected_comp_values = MakeSet(PackProbedString(self.bom, comp_cls))
      extra_components = probed_comp_values - expected_comp_values
      missing_components = expected_comp_values - probed_comp_values
      if extra_components or missing_components:
        raise HWIDException(
            'Component class %r has extra components: %r and missing '
            'components: %r. Expected values are: %r' %
            (comp_cls, sorted(extra_components), sorted(missing_components),
             sorted(expected_comp_values)))


class BOM(object):
  """A class that holds all the information regarding a BOM.

  Attributes:
    board: A string of board name.
    encoding_pattern_index: An int indicating the encoding pattern. Currently,
        only 0 is used.
    image_id: An int indicating the image id.
    components: A dict that maps component classes to a list of
        ProbedComponentResult.
    encoded_fields: A dict that maps each encoded field to its index.

  Raises:
    SchemaException if invalid argument format is found.
  """
  _COMPONENTS_SCHEMA = Dict(
      'bom',
      key_type=Scalar('component class', str),
      value_type=List(
          'list of ProbedComponentResult',
          Tuple('ProbedComponentResult',
                [Optional(Scalar('component name', str)),
                 Optional(Scalar('probed string', str)),
                 Optional(Scalar('error', str))])))

  def __init__(self, board, encoding_pattern_index, image_id,
               components, encoded_fields):
    self.board = board
    self.encoding_pattern_index = encoding_pattern_index
    self.image_id = image_id
    self.components = components
    self.encoded_fields = encoded_fields
    BOM._COMPONENTS_SCHEMA.Validate(self.components)

  def Duplicate(self):
    """Duplicates this BOM object.

    Returns:
      A deepcopy of the original BOM object.
    """
    return copy.deepcopy(self)

class Database(object):
  """A class for reading in, parsing, and obtaining information of the given
  device-specific component database.

  Attributes:
    board: A string indicating the board name.
    encoding_patterns: A _EncodingPatterns object.
    image_id: A _ImageId object.
    pattern: A _Pattern object.
    encoded_fields: A _EncodedFields object.
    probeable_components: A _ProbeableComponents objet.
    components: A _Components object.
    shopfloor_device_info: A ShopFloorDeviceInfo object.
    vpd_ro_field: A _VPDFields object.
    vpd_rw_field: A _VPDFields object.
    rules: A list of rules of the form:
        [
          {
            'name': 'rule1',
            'when': ['condition1', 'condition2', ...],
            'check_all' or 'check_any': ['condition1', 'condition2', ...]
          },
          {
            'name': 'rule2',
            ...
          }
          ...
        ]
    allowed_skus: A list of allowed SKUs of the form:
        [
          {
            'name': 'sku1',
            'check_all': ['condition1', 'condition2', ...]
          }
          {
            'name': 'sku2',
            ...
          }
          ...
        ]
  """
  # TODO(jcliang): Change back in R27.
  #_HWID_FORMAT = re.compile(r'^([A-Z0-9]+) ((?:[A-Z2-7]{4}-)*[A-Z2-7]{1,4})$')
  _HWID_FORMAT = re.compile(
      r'^([A-Z0-9]+) ((?:[A-Z2-7]{4}-)*[A-Z2-7]{1,4}) ([0-9]+)$')

  def __init__(self, board, encoding_patterns, image_id, pattern,
               encoded_fields, probeable_components, components,
               shopfloor_device_info, vpd_ro_fields, vpd_rw_fields,
               rules, allowed_skus):
    self.board = board
    self.encoding_patterns = encoding_patterns
    self.image_id = image_id
    self.pattern = pattern
    self.encoded_fields = encoded_fields
    self.probeable_components = probeable_components
    self.components = components
    self.shopfloor_device_info = shopfloor_device_info
    self.vpd_ro_fields = vpd_ro_fields
    self.vpd_rw_fields = vpd_rw_fields
    self.rules = rules
    self.allowed_skus = allowed_skus
    self._SanityChecks()

  def _SanityChecks(self):
    def _VerifyComponent(comp_cls, comp_name, label):
      if comp_cls not in self.components:
        raise HWIDException(
            'Invalid component class %r in %s' % (comp_cls, label) )
      if comp_name and comp_name not in self.components[comp_cls]:
        raise HWIDException(
            'Invalid component name %r in %s[%r]' %
            (comp_name, label, comp_cls))

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

    # Check that all the component class-name pairs in shopfloor_device_info are
    # valid.
    for info_key, info_value_dict in self.shopfloor_device_info.iteritems():
      for info_value, class_name_dict in info_value_dict.iteritems():
        for comp_cls, comp_names in class_name_dict.iteritems():
          if comp_names is None:
            _VerifyComponent(
                comp_cls, None,
                'shopfloor_device_info[%r][%r]' % (info_key, info_value))
          else:
            for comp_name in comp_names:
              _VerifyComponent(
                  comp_cls, comp_name,
                  'shopfloor_device_info[%r][%r]' % (info_key, info_value))

    # Check that all the component classes in probeable_components are valid.
    for comp_cls in self.probeable_components:
      _VerifyComponent(comp_cls, None, 'probeable_components')

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
    with open(file_name, 'r+') as f:
      db_yaml = yaml.load(f)

    for key in ['board', 'encoding_patterns', 'image_id', 'pattern',
                'encoded_fields', 'probeable_components', 'components',
                'shopfloor_device_info', 'vpd_ro_fields', 'vpd_rw_fields']:
      if not db_yaml.get(key):
        raise HWIDException('%r is not specified in component database' % key)

    rules = db_yaml.get('rules')
    allowed_skus = db_yaml.get('allowed_skus')
    # Temporary schema validations for rules and skus.
    # TODO(jcliang): Update these schema checks after rule language refacoring.
    if rules:
      rules_schema = List('list of rules', FixedDict('rules',
          items={
              'name': Scalar('rule name', str),
              'when': List('conditions', Scalar('condition', str))},
          optional_items={
              'check_all': List('rules', AnyOf([
                  Scalar('condition', str),
                  Dict('recursive rule',
                       key_type=Scalar('sub-rule', str),
                       value_type=List('list of rules'))])),
              'check_any': List('rules', AnyOf([
                  Scalar('condition', str),
                  Dict('recursive rule',
                       key_type=Scalar('sub-rule', str),
                       value_type=List('list of rules'))]))}))
      rules_schema.Validate(rules)
    if allowed_skus:
      allowed_skus_schema = List('list of skus', FixedDict('skus',
          items={
              'name': Scalar('sku name', str),
              'check_all': List('conditions', Scalar('condition', str))},
          optional_items=None))
      allowed_skus_schema.Validate(allowed_skus)

    return Database(db_yaml['board'],
                    _EncodingPatterns(db_yaml['encoding_patterns']),
                    _ImageId(db_yaml['image_id']), _Pattern(db_yaml['pattern']),
                    _EncodedFields(db_yaml['encoded_fields']),
                    _ProbeableComponents(db_yaml['probeable_components']),
                    _Components(db_yaml['components']),
                    ShopFloorDeviceInfo(db_yaml['shopfloor_device_info']),
                    _VPDFields(db_yaml['vpd_ro_fields']),
                    _VPDFields(db_yaml['vpd_rw_fields']),
                    rules, allowed_skus)

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
          return MakeList(probed_bom[field][comp_cls])
      # comp_cls is in probed_bom['missing_component_classes'].
      return None

    # Construct a dict of component classes to list of ProbedComponentResult.
    probed_components = collections.defaultdict(list)
    for comp_cls in self.components:
      probed_comp_values = LookupProbedValue(comp_cls)
      if probed_comp_values is not None:
        for probed_value in probed_comp_values:
          if comp_cls not in self.probeable_components:
            probed_components[comp_cls].append(
                ProbedComponentResult(
                    None, probed_value, 'component class %r is unprobeable' %
                    comp_cls))
            continue
          found = False
          for comp_name, comp_attrs in self.components[comp_cls].iteritems():
            if comp_attrs['value'] == probed_value:
              probed_components[comp_cls].append(
                  ProbedComponentResult(comp_name, probed_value, None))
              found = True
              break
          if not found:
            probed_components[comp_cls].append(
                ProbedComponentResult(None, probed_value, (
                    'unsupported %r component found with probe result'
                    ' %r (no matching name in the component DB)' %
                    (comp_cls, probed_value))))
      else:
        # No component of comp_cls is found in probe results.
        probed_components[comp_cls].append(
            ProbedComponentResult(None, probed_comp_values,
                                  'missing %r component' % comp_cls))

    # Encode the components to a dict of encoded fields to encoded indices.
    encoded_fields = {}
    for field in self.encoded_fields:
      encoded_fields[field] = self._GetFieldIndexFromProbedComponents(
          field, probed_components)

    return BOM(self.board, encoding_pattern_index, image_id, probed_components,
               encoded_fields)

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
    for component_class, component_name in updated_components.iteritems():
      new_probed_result = []
      if component_name is None:
        new_probed_result.append(ProbedComponentResult(
            None, None, 'missing %r component' % component_class))
      else:
        component_name = MakeList(component_name)
        for name in component_name:
          try:
            new_probed_result.append(ProbedComponentResult(
                name, self.components[component_class][name]['value'], None))
          except KeyError:
            raise HWIDException(
                'Component {%r: %r} is not defined in the component database' %
                (component_class, name))
      # Update components data of the duplicated BOM.
      result.components[component_class] = new_probed_result

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
              probed_components[db_comp_cls][0].probed_string is not None):
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
          new_attr = dict(self.components[comp_cls][name])
          new_attr['name'] = name
          result[comp_cls].append(new_attr)
    return result

  def VerifyBinaryString(self, binary_string):
    """Verifies the binary string.

    Raises:
      HWIDException if verification fails.
    """
    if set(binary_string) - set('01'):
      raise HWIDException('Invalid binary string: %r' % binary_string)

    if '1' not in binary_string:
      raise HWIDException('Binary string %r does not have stop bit set',
                          binary_string)
    # Truncate trailing 0s.
    string_without_paddings = binary_string[:binary_string.rfind('1') + 1]

    if len(string_without_paddings) > self.pattern.GetTotalBitLength():
      raise HWIDException('Invalid bit string length of %r. Expected '
                          'length <= %d, got length %d' %
                          (binary_string, self.pattern.GetTotalBitLength(),
                           len(string_without_paddings)))

  def VerifyEncodedString(self, encoded_string):
    """Verifies the encoded string.

    Raises:
      HWIDException if verification fails.
    """
    try:
      # TODO(jcliang): Change back in R27.
      #board, bom_checksum = Database._HWID_FORMAT.findall(encoded_string)[0]
      board, bom_checksum, dummy_checksum = (
          Database._HWID_FORMAT.findall(encoded_string)[0])
    except IndexError:
      raise HWIDException('Invalid HWID string format: %r' % encoded_string)
    if len(bom_checksum) < 2:
      raise HWIDException(
          'Length of encoded string %r is less than 2 characters' %
          bom_checksum)
    if not board == self.board.upper():
      raise HWIDException('Invalid board name: %r' % board)
    # Verify the checksum
    stripped = encoded_string.replace('-', '')
    # TODO(jcliang): Change back in R27.
    # Remove dummy checksum.
    stripped = stripped[:-5]
    hwid = stripped[:-2]
    checksum = stripped[-2:]
    expected_checksum = Base32.Checksum(hwid)
    if not checksum == Base32.Checksum(hwid):
      raise HWIDException('Checksum of %r mismatch (expected %r)' % (
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
      raise HWIDException('Missing component classes: %r',
                          ', '.join(sorted(missing_comp)))

    bom_encoded_fields = MakeSet(bom.encoded_fields.keys())
    db_encoded_fields = MakeSet(self.encoded_fields.keys())
    # Every encoded field defined in the database must present in BOM.
    if db_encoded_fields - bom_encoded_fields:
      raise HWIDException('Missing encoded fields in BOM: %r',
                          ', '.join(sorted(db_encoded_fields -
                                           bom_encoded_fields)))
    # Every encoded field the BOM has must exist in the database.
    if bom_encoded_fields - db_encoded_fields:
      raise HWIDException('Extra encoded fields in BOM: %r',
                          ', '.join(sorted(bom_encoded_fields -
                                           db_encoded_fields)))

    if bom.board != self.board:
      raise HWIDException('Invalid board name. Expected %r, got %r' %
                          (self.board, bom.board))

    if bom.encoding_pattern_index not in self.encoding_patterns:
      raise HWIDException('Invalid encoding pattern: %r' %
                          bom.encoding_pattern_index)
    if bom.image_id not in self.image_id:
      raise HWIDException('Invalid image id: %r' % bom.image_id)

    # All the probeable component values in the BOM should exist in the
    # database.
    unknown_values = []
    for comp_cls, probed_values in bom.components.iteritems():
      for element in probed_values:
        probed_value = element.probed_string
        if probed_value is None or comp_cls not in self.probeable_components:
          continue
        found = False
        for attrs in self.components[comp_cls].itervalues():
          if attrs['value'] == probed_value:
            found = True
            break
        if not found:
          unknown_values.append('%s:%s' % (comp_cls, probed_value))
    if unknown_values:
      raise HWIDException('Unknown component values: %r' %
                          ', '.join(sorted(unknown_values)))

    # All the encoded index should exist in the database.
    invalid_fields = []
    for field, index in bom.encoded_fields.iteritems():
      if index is not None and index not in self.encoded_fields[field]:
        invalid_fields.append(field)
    if invalid_fields:
      raise HWIDException('Encoded fields %r have unknown indices' %
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
          probed_string,   # The actual probed string. None if probing failed.
          error)]}         # The error message if there is one; else None.
    """
    probed_bom = self.ProbeResultToBOM(probe_result)
    if comp_list is None:
      comp_list = self.probeable_components
    if not isinstance(comp_list, list):
      raise HWIDException('Argument comp_list should be a list')
    invalid_cls = set(comp_list) - set(self.probeable_components)
    if invalid_cls:
      raise HWIDException('%r is not probeable and cannot be verified' %
                          sorted(invalid_cls))
    return dict((comp_cls, probed_bom.components[comp_cls]) for comp_cls in
                comp_list)

class _EncodingPatterns(dict):
  """Class for parsing encoding_patterns in database.

  Args:
    encoding_patterns_dict: A dict of encoding patterns of the form:
        {
          0: 'default',
          1: 'extra_encoding_pattern',
          ...
        }
        schema:
          Dict('encoding patterns',
               key_type=Scalar('encoding pattern', int),
               value_type=Scalar('encoding scheme', str))
  """
  def __init__(self, encoding_patterns_dict):
    self.schema = Dict('encoding patterns',
                       key_type=Scalar('encoding pattern', int),
                       value_type=Scalar('encoding scheme', str))
    self.schema.Validate(encoding_patterns_dict)
    super(_EncodingPatterns, self).__init__(encoding_patterns_dict)


class _ImageId(dict):
  """Class for parsing image_id in database.

  Args:
    image_id_dict: A dict of image ids of the form:
        {
          0: 'image_id0',
          1: 'image_id1',
          ...
        }
        schema:
          Dict('image id',
               key_type=Scalar('image id', int),
               value_type=Scalar('image name', str))
  """
  def __init__(self, image_id_dict):
    self.schema = Dict('image id',
                       key_type=Scalar('image id', int),
                       value_type=Scalar('image name', str))
    self.schema.Validate(image_id_dict)
    super(_ImageId, self).__init__(image_id_dict)


class _EncodedFields(dict):
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
        schema:
          Dict('encoded fields', Scalar('encoded field', str),
            Dict('encoded indices', Scalar('encoded index', int),
              Dict('component classes', Scalar('component class', str),
                Optional([Scalar('component name', str),
                          List('list of component names',
                               Scalar('component name', str))]
                )
              )
            )
          )
  """
  def __init__(self, encoded_fields_dict):
    self.schema = Dict(
      'encoded fields',
      Scalar('encoded field', str),
      Dict('encoded indices',
           Scalar('encoded index', int),
           Dict('component classes',
                Scalar('component class', str),
                Optional([Scalar('component name', str),
                          List('list of component names',
                               Scalar('component name', str))])
                )
           )
      )
    self.schema.Validate(encoded_fields_dict)
    super(_EncodedFields, self).__init__(encoded_fields_dict)
    # Convert string to list of string.
    for field in self:
      for index in self[field]:
        for comp_cls in self[field][index]:
          comp_value = self[field][index][comp_cls]
          if isinstance(comp_value, str):
            self[field][index][comp_cls] = MakeList(comp_value)


class _ProbeableComponents(list):
  """A class for storing the set of components that are probeable.

  Args:
    probeable_component_list: A list of strings indicating the probeable
        component classes.
  """
  def __init__(self, probeable_component_list):
    self.schema = List('probeable components', Scalar('component class', str))
    self.schema.Validate(probeable_component_list)
    super(_ProbeableComponents, self).__init__(probeable_component_list)


class _Components(dict):
  """A class for parsing and obtaining information of a pre-defined components
  list.

  Args:
    components_dict: A dict of components of the form:
        {
          'component_class1': {
            'component_name1': {
              'value': 'component_value1',
              'other_attributes': 'other values',
              ...
            }
            'component_name2': {
              ...
            }
          }
          'component_class2': {
            ...
          }
        }
        schema:
          Dict('components', Scalar('component class', str),
            Dict('component names', Scalar('component name', str),
              FixedDict('component attributes', items={
                'value': AnyOf([Scalar('probed value', str),
                                List('list of probed values',
                                     Scalar('probed value', str))])
                },
                optional_items={
                  'labels': List('list of labels', Scalar('label', str))
                }
              )
            )
          )
  """
  def __init__(self, components_dict):
    self.schema = Dict(
        'components',
        Scalar('component class', str),
        Dict('component names',
             Scalar('component name', str),
             FixedDict(
                 'component attributes',
                 items={'value': Optional(
                     [Scalar('probed value', str),
                      List('list of probed values',
                           Scalar('probed value', str))])},
                 optional_items={'labels': List('list of labels',
                                                Scalar('label', str))})))
    self.schema.Validate(components_dict)
    super(_Components, self).__init__(components_dict)


class _Pattern(object):
  """A class for parsing and obtaining information of a pre-defined encoding
  pattern.

  Args:
    pattern_list: A list of dicts that maps encoded fields to their
        bit length.
        schema:
          List('pattern',
            Dict('pattern_field', {
              Scalar('encoded_index', str): Scalar('bit_offset', int)
            })
          )
  """
  def __init__(self, pattern_list):
    self.schema = List('pattern',
          Dict('pattern field', key_type=Scalar('encoded index', str),
               value_type=Scalar('bit offset', int)))
    self.schema.Validate(pattern_list)
    self.pattern = pattern_list

  def GetFieldsBitLength(self):
    """Gets a map for the bit length of each encoded fields defined by the
    pattern. Scattered fields with the same field name are aggregated into one.

    Returns:
      A dict mapping each encoded field to its bit length.
    """
    if self.pattern is None:
      raise HWIDException(
          'Cannot get encoded field bit length with uninitialized pattern')
    ret = collections.defaultdict(int)
    for element in self.pattern:
      for cls, length in element.iteritems():
        ret[cls] += length
    return ret

  def GetTotalBitLength(self):
    """Gets the total bit length of defined by the pattern. Common header and
    stopper bit are included.

    Returns:
      A int indicating the total bit length.
    """
    if self.pattern is None:
      raise HWIDException(
          'Cannot get bit length with uninitialized pattern')
    # 5 bits for header and 1 bit for stop bit
    return HWID.HEADER_BITS + 1 + sum(self.GetFieldsBitLength().values())

  def GetBitMapping(self):
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
      raise HWIDException(
          'Cannot construct bit mapping with uninitialized pattern')
    ret = {}
    index = HWID.HEADER_BITS   # Skips the 5-bit common header.
    field_offset_map = collections.defaultdict(int)
    for element in self.pattern:
      for field, length in element.iteritems():
        for _ in xrange(length):
          ret[index] = BitEntry(field, field_offset_map[field])
          field_offset_map[field] += 1
          index += 1
    return ret


class ShopFloorDeviceInfo(dict):
  """A class for storing device info mapping sent by shopfloor.

  We often need to ask shopfloor for device info, and the response is usually a
  dict of device info keys to info values. This class is used to map component
  info to its corresponding component name.

  Args:
    shopfloor_device_info_dict: A dict of device info keys to their
        corresponding component class-component name pairs. For example:

        {'has_cellular': {
            'yes': {cellular: cellular_0},
            'no': {cellular: None}
        }}

        means that if the value of 'has_cellular' info key is 'yes', then
        'cellular' component should be 'cellular_0'; if it's 'no', then
        'cellular' component should be None.
  """
  def __init__(self, shopfloor_device_info_dict):
    self.schema = Dict(
        'shopfloor device info',
        key_type=Scalar('device info key', str),
        value_type=Dict(
            'value to operation mapping',
            key_type=AnyOf(
                [Scalar('value string', str),
                 Scalar('boolean', bool)],
                label='device info value'),
            value_type=Dict(
                'component classes to names',
                key_type=Scalar('component class', str),
                value_type=Optional(
                    [Scalar('component name', str),
                     List('list of component names',
                          Scalar('component name', str))]))))
    self.schema.Validate(shopfloor_device_info_dict)
    super(ShopFloorDeviceInfo, self).__init__(shopfloor_device_info_dict)
    # Convert string to list of string.
    for info_key in self:
      for info_value in self[info_key]:
        for comp_cls in self[info_key][info_value]:
          comp_value = self[info_key][info_value][comp_cls]
          if isinstance(comp_value, str):
            self[info_key][info_value][comp_cls] = MakeList(comp_value)


class _VPDFields(list):
  """A class for storing the required VPD fields.

  Args:
    vpd_field_list: A list of strings indicating the required VPD fields.
  """
  def __init__(self, vpd_field_list):
    self.schema = List('vpd fields', Scalar('vpd field', str))
    self.schema.Validate(vpd_field_list)
    super(_VPDFields, self).__init__(vpd_field_list)
