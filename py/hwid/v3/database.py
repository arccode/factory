# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Database classes for HWID v3 operation.

The HWID database for a Chromebook project defines how to generate (or
to say, encode) a HWID encoded string for the Chromebook.  The HWID database
contains many parts:

  1. `components` lists information of all hardware components.
  2. `encoded_fields` maps each hardware component's name to a number to be
     encoded into the HWID encoded string.
  3. `pattern` records the ways to union all numbers together to form an unique
     fixed-bit-length number which responses to a set of hardware components.
     `pattern` records many different ways to union numbers because the
     bit-length of the number might not be enough after new hardware
     components are added into the Database.
  4. `image_id` lists all possible image ids.  An image id consists of an
     index (start from 0) and a human-readable name.  The name of an image id
     often looks similar to the factory build stage, but it's not necessary.
     There's an one-to-one mapping relation between the index of an image id
     and the pattern so that we know which pattern to apply for encode/decode
     the numbers/HWID encode string.
  5. `encoded_patterns` is a reserved bit and it can only be 0 now.
  6. `project` records the name of the Chromebook project.
  7. `checksum` records a checksum string to make sure that the Database is not
     modified.
  8. `rules` records a list of rules to be evaluated during generating the HWID
     encoded string.

This package implements some basic methods for manipulating a HWID database
and the loader to load the database from a file.  The classes in this package
represents to each part of the HWID database listed above.  The detail of
each part is described in the class' document.
"""

import collections
import copy
import hashlib
import logging
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.rule import Rule
from cros.factory.hwid.v3.rule import Value
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import file_utils
from cros.factory.utils import schema
from cros.factory.utils import type_utils


class Database(object):
  """A class for reading in, parsing, and obtaining information of the given
  device-specific component database.

  Attributes:
    _project: A string indicating the project name.
    _encoding_patterns: An EncodingPatterns object.
    _image_id: An ImageId object.
    _pattern: A Pattern object.
    _encoded_fields: An EncodedFields object.
    _components: A Components object.
    _rules: A Rules object.
    _checksum: None or a string of the value of the checksum field.
  """

  def __init__(self, project, encoding_patterns, image_id, pattern,
               encoded_fields, components, rules, checksum):
    """Constructor.

    This constructor should not be called by other modules.
    """
    self._project = project
    self._encoding_patterns = encoding_patterns
    self._image_id = image_id
    self._pattern = pattern
    self._encoded_fields = encoded_fields
    self._components = components
    self._rules = rules
    self._checksum = checksum

    self._SanityChecks()

  def __eq__(self, rhs):
    # pylint: disable=protected-access
    return (isinstance(rhs, Database) and
            self._project == rhs._project and
            self._encoding_patterns == rhs._encoding_patterns and
            self._image_id == rhs._image_id and
            self._encoded_fields == rhs._encoded_fields and
            self._components == rhs._components and
            self._checksum == rhs._checksum)

  def __ne__(self, rhs):
    return not self == rhs

  @staticmethod
  def LoadFile(file_name, verify_checksum=True):
    """Loads a device-specific component database from the given file and
    parses it to a Database object.

    Args:
      file_name: A path to a device-specific component database.
      verify_checksum: Whether to verify the checksum of the database.

    Returns:
      A Database object containing all the settings in the database file.

    Raises:
      HWIDException if there is missing field in the database.
    """
    return Database.LoadData(file_utils.ReadFile(file_name),
                             expected_checksum=(Database.Checksum(file_name)
                                                if verify_checksum else None))

  @staticmethod
  def Checksum(file_name):
    """Computes a SHA1 digest as the checksum of the given database file.

    Args:
      file_name: A path to a device-specific component database.

    Returns:
      The computed checksum as a string.
    """
    return Database.ChecksumForText(file_utils.ReadFile(file_name))

  @staticmethod
  def ChecksumForText(db_text):
    """Computes a SHA1 digest as the checksum of the given database string.

    Args:
      db_text: The database as a string.

    Returns:
      The computed checksum as a string.
    """
    # Ignore the 'checksum: <hash value>\n' line when calculating checksum.
    db_text = re.sub(r'^checksum:.*$\n?', '', db_text, flags=re.MULTILINE)
    return hashlib.sha1(db_text).hexdigest()

  @staticmethod
  def LoadData(raw_data, expected_checksum=None):
    """Loads a device-specific component database from the given database data.

    Args:
      raw_data: The database in string.
      expected_checksum: The checksum value to verify the loaded data with.
          A value of None disables checksum verification.

    Returns:
      A Database object containing all the settings in the database file.

    Raises:
      HWIDException if there is missing field in the database, or database
      integrity veification fails.
    """
    yaml_obj = yaml.load(raw_data)

    if not isinstance(yaml_obj, dict):
      raise common.HWIDException('Invalid HWID database')

    if 'board' in yaml_obj and 'project' not in yaml_obj:
      yaml_obj['project'] = yaml_obj['board']

    for key in ['project', 'encoding_patterns', 'image_id', 'pattern',
                'encoded_fields', 'components', 'rules', 'checksum']:
      if key not in yaml_obj:
        raise common.HWIDException(
            '%r is not specified in HWID database' % key)

    project = yaml_obj['project'].upper()
    if project != yaml_obj['project']:
      logging.warning('The project name should be in upper cases, but got %r.',
                      yaml_obj['project'])

    # Verify database integrity.
    if (expected_checksum is not None and
        yaml_obj['checksum'] != expected_checksum):
      raise common.HWIDException(
          'HWID database %r checksum verification failed' % project)

    return Database(project,
                    EncodingPatterns(yaml_obj['encoding_patterns']),
                    ImageId(yaml_obj['image_id']),
                    Pattern(yaml_obj['pattern']),
                    EncodedFields(yaml_obj['encoded_fields']),
                    Components(yaml_obj['components']),
                    Rules(yaml_obj['rules']),
                    yaml_obj.get('checksum'))

  def DumpData(self, include_checksum=False):
    all_parts = [
        ('checksum', self._checksum if include_checksum else None),
        ('project', self._project),
        ('encoding_patterns', self._encoding_patterns.Export()),
        ('image_id', self._image_id.Export()),
        ('pattern', self._pattern.Export()),
        ('encoded_fields', self._encoded_fields.Export()),
        ('components', self._components.Export()),
        ('rules', self._rules.Export()),
    ]

    return '\n'.join([yaml.dump({key: value}, default_flow_style=False)
                      for key, value in all_parts])

  def DumpFile(self, path, include_checksum=False):
    with open(path, 'w') as f:
      f.write(self.DumpData(include_checksum=include_checksum))

  @property
  def can_encode(self):
    return self._components.can_encode and self._encoded_fields.can_encode

  @property
  def project(self):
    return self._project

  @property
  def checksum(self):
    return self._checksum

  @property
  def encoding_patterns(self):
    return self._encoding_patterns.keys()

  @property
  def image_ids(self):
    return self._image_id.keys()

  @property
  def max_image_id(self):
    return self._image_id.max_image_id

  @property
  def rma_image_id(self):
    return self._image_id.rma_image_id

  def GetImageName(self, image_id):
    return self._image_id[image_id]

  def AddImage(self, image_id, image_name, encoding_scheme,
               new_pattern=False):
    if new_pattern:
      self._pattern.AddEmptyPattern(image_id, encoding_scheme)
    else:
      self._pattern.AddImageId(self.max_image_id, image_id)
    self._image_id[image_id] = image_name

  def GetImageIdByName(self, image_name):
    return self._image_id.GetImageIdByName(image_name)

  def GetEncodingScheme(self, image_id=None):
    return self._pattern.GetEncodingScheme(image_id)

  def GetTotalBitLength(self, image_id=None):
    return self._pattern.GetTotalBitLength(image_id)

  def GetEncodedFieldsBitLength(self, image_id=None):
    return self._pattern.GetFieldsBitLength(image_id)

  def GetBitMapping(self, image_id=None, max_bit_length=None):
    return self._pattern.GetBitMapping(image_id, max_bit_length)

  def AppendEncodedFieldBit(self, field_name, bit_length, image_id=None):
    if field_name not in self.encoded_fields:
      raise common.HWIDException('The field %r does not exist.' % field_name)

    self._pattern.AppendField(field_name, bit_length, image_id=image_id)

  @property
  def encoded_fields(self):
    return self._encoded_fields.encoded_fields

  def GetEncodedField(self, encoded_field_name):
    return self._encoded_fields.GetField(encoded_field_name)

  def GetComponentClasses(self, encoded_field_name=None):
    """Returns a set of component class names with optional conditions.

    If `encoded_field_name` is specified, this function only returns the
    component classes which will be encoded by the specific encoded field.
    If `encoded_field_name` is not specified, this function returns all
    component classes recorded by the database.

    Args:
      encoded_field_name: None of a string of the name of the encoded field.

    Returns:
      A set of component class names.
    """
    if encoded_field_name:
      return self._encoded_fields.GetComponentClasses(encoded_field_name)

    ret = set(self._components.component_classes)
    for encoded_field_name in self.encoded_fields:
      ret |= set(self._encoded_fields.GetComponentClasses(encoded_field_name))

    return ret

  def GetEncodedFieldForComponent(self, comp_cls):
    return self._encoded_fields.GetFieldForComponent(comp_cls)

  def AddNewEncodedField(self, encoded_field_name, components):
    self._VerifyEncodedFieldComponents(components)

    self._encoded_fields.AddNewField(encoded_field_name, components)

  def AddEncodedFieldComponents(self, encoded_field_name, components):
    self._VerifyEncodedFieldComponents(components)

    self._encoded_fields.AddFieldComponents(encoded_field_name, components)

  def GetComponents(self, comp_cls, include_default=True):
    """Gets the components of the specific component class.

    Args:
      comp_cls: A string of the name of the component class.
      include_default: True to include the default component (the component
          which values is `None` instead of a dictionary) in the return
          components.

    Returns:
      A dict which maps a string of component name to a `ComponentInfo` object,
      which is a named tuple contains two attributes:
        values: A string-to-string dict of expected probed results.
        status: One of "unsupported", "deprecated", "unqualified", "supported".
    """
    comps = self._components.GetComponents(comp_cls)
    if not include_default:
      comps = {name: info for name, info in comps.iteritems()
               if info.values is not None}
    return comps

  def GetDefaultComponent(self, comp_cls):
    return self._components.GetDefaultComponent(comp_cls)

  def AddComponent(self, comp_cls, comp_name, value, status):
    return self._components.AddComponent(comp_cls, comp_name, value, status)

  def SetComponentStatus(self, comp_cls, comp_name, status):
    return self._components.SetComponentStatus(comp_cls, comp_name, status)

  @property
  def device_info_rules(self):
    return self._rules.device_info_rules

  @property
  def verify_rules(self):
    return self._rules.verify_rules

  def AddDeviceInfoRule(self, name_suffix, evaluate, **kwargs):
    self._rules.AddDeviceInfoRule(name_suffix, evaluate, **kwargs)

  def GetActiveComponentClasses(self, image_id=None):
    ret = set()
    for encoded_field_name in self.GetEncodedFieldsBitLength(image_id).keys():
      ret |= self.GetComponentClasses(encoded_field_name)

    return ret

  def _SanityChecks(self):
    # Each image id should have a corresponding pattern.
    if set(self.image_ids) != set(self._pattern.all_image_ids):
      raise common.HWIDException(
          'Each image id should have a corresponding pattern.')

    # Encoded fields should be well defined.
    for image_id in self.image_ids:
      for encoded_field_name in self.GetEncodedFieldsBitLength(image_id):
        if encoded_field_name not in self.encoded_fields:
          raise common.HWIDException(
              'The encoded field %r is not defined in `encoded_fields` part.' %
              encoded_field_name)

    # Each encoded field should be well defined.
    for encoded_field_name in self.encoded_fields:
      for comps in self.GetEncodedField(encoded_field_name).itervalues():
        for comp_cls, comp_names in comps.iteritems():
          missing_comp_names = (
              set(comp_names) - set(self.GetComponents(comp_cls).keys()))
          if missing_comp_names:
            raise common.HWIDException(
                'The components %r are not defined in `components` part.' %
                missing_comp_names)

  def _VerifyEncodedFieldComponents(self, components):
    for comp_cls, comp_names in components.iteritems():
      for comp_name in comp_names:
        if comp_name not in self.GetComponents(comp_cls):
          raise common.HWIDException('The component %r is not recorded '
                                     'in `components` part.' % comp_name)


class _NamedNumber(dict):
  """A customized dictionary for `encoding_patterns` and `image_id` parts.

  This class limits some features of the build-in dict to keep the HWID
  database valid.  The restrictions are:
    1. Key of this dictionary must be an integer.
    2. Value of this dictionary must be an unique string.
    3. Existed key-value cannot be modified or be removed.
  """

  PART_TAG = None
  NUMBER_RANGE = None
  NUMBER_TAG = None
  NAME_TAG = None

  def __init__(self, source):
    super(_NamedNumber, self).__init__()

    if not isinstance(source, dict):
      raise common.HWIDException(
          'Invalid source %r for `%s` part of a HWID database.' %
          (source, self.PART_TAG))

    for number, name in source.iteritems():
      self[number] = name

  def Export(self):
    """Exports to a dictionary which can be saved into the database file."""
    return dict(self)

  def __getitem__(self, number):
    """Gets the name of the specific number.

    Raises:
      common.HWIDException if the given number is not recorded.
    """
    try:
      return super(_NamedNumber, self).__getitem__(number)
    except KeyError:
      raise common.HWIDException(
          'The %s %r is not recorded.' % (self.NUMBER_TAG, number))

  def __setitem__(self, number, name):
    """Adds a new number or updates an existed number's name.

    Raises:
      common.HWIDException if failed.
    """
    # pylint:disable=unsupported-membership-test
    if number not in self.NUMBER_RANGE:
      raise common.HWIDException('The %s should be one of %r, but got %r.' %
                                 (self.NUMBER_TAG, self.NUMBER_RANGE, number))

    if not isinstance(name, str):
      raise common.HWIDException('The %s should be a string, but got %r.' %
                                 (self.NAME_TAG, name))

    if number in self:
      raise common.HWIDException('The %s %r already exists.' %
                                 (self.NUMBER_TAG, number))

    if name in self.values():
      raise common.HWIDException('The %s %r is already in used.' %
                                 (self.NAME_TAG, name))

    super(_NamedNumber, self).__setitem__(number, name)

  def __delitem__(self, key):
    raise common.HWIDException(
        'Invalid operation: remove %s %r.' % (self.NUMBER_TAG, key))


class EncodingPatterns(_NamedNumber):
  """Class for holding `encoding_patterns` part in a HWID database.

  `encoding_patterns` part records all encoding pattern ids and their unique
  name.

  An encoding pattern id is either 0 or 1 (1 bit in width).  But since the
  encoding method is not defined for the encoding pattern id being 1, this
  value now can only be 0.

  In the HWID database file, `encoding_patterns` part looks like:

  ```yaml
  encoding_patterns:
    0: default  # 0 is the encoding pattern id, "default" is the
                # encoding pattern name.

  ```
  """
  PART_TAG = 'encoding_patterns'
  NUMBER_RANGE = [0]
  NUMBER_TAG = 'encoding pattern id'
  NAME_TAG = 'encoding pattern name'


class ImageId(_NamedNumber):
  """Class for holding `image_id` part in a HWID database.

  `image_id` part in a HWID database records all image ids and their name.

  An image id is an integer between 0~15 (4 bits in width).  Each image id has
  an unique name (called image name) in string.  This class is a dictionary
  mapping each image id to the corresponding image name.

  In the HWID database file, `image_id` part looks like:

  ```yaml
  image_id:
    0: PROTO    # 0 is the image id, "PROTO" is the image name.
    1: EVT      # 1 is another image id.
    2: EVT-99
    3: WA_LALA
    ...

  ```
  """
  PART_TAG = 'image_id'
  NUMBER_RANGE = range(1 << common.IMAGE_ID_BIT_LENGTH)
  NUMBER_TAG = 'image id'
  NAME_TAG = 'image name'

  RMA_IMAGE_ID = max(NUMBER_RANGE)
  """Preserve the max image ID for RMA pattern."""

  def GetImageIdByName(self, image_name):
    """Returns the image id of the given image name.

    Raises:
      common.HWIDException if the image id is not found.
    """
    for i, name in self.iteritems():
      if name == image_name:
        return i

    raise common.HWIDException('The image name %r is not valid.' % image_name)

  @property
  def max_image_id(self):
    """Returns the maximum image id."""
    return self.GetMaxImageIDFromList(self.keys())

  @property
  def rma_image_id(self):
    return self.GetRMAImageIDFromList(self.keys())

  @classmethod
  def GetMaxImageIDFromList(cls, image_ids):
    return max(set(image_ids) - {cls.RMA_IMAGE_ID})

  @classmethod
  def GetRMAImageIDFromList(cls, image_ids):
    if cls.RMA_IMAGE_ID in image_ids:
      return cls.RMA_IMAGE_ID
    return None


class EncodedFields(object):
  """Class for holding `encoded_fields` part of a HWID database.

  `encoded_fields` part of a HWID database defines the way to convert
  hardware components to numbers (and then `pattern` part defines way to union
  all numbers (each encoded field generates a number) together).

  `encoded_fields` defines a set of encoded field.  Each encoded field contains
  a set of numbers.  A number then maps to a hardware component, or a set
  of hardware components.  For example, in the HWID database file, this part
  might look like:

  ```yaml
  encoded_fields:
    wireless_field:
      0:
        wireless: super_cool_wireless_component
      1:
        wireless: not_so_good_component
    dram_field:
      0:
        dram:
        - ram_4g_1
        - ram_4g_2
      1:
        dram:
        - ram_8g_1
        - ram_8g_2
    firmware_field:
      0:
        ec_firmware: ec_rev0
        main_firmware: main_rev0
      1:
        ec_firmware: ec_rev0
        main_firmware: main_rev1
      2:
        ec_firmware: ec_rev0
        main_firmware: main_rev2
    chassis_field:
      0:
        chassis: COOL_CHASSIS_ID
  ```
  If the Chromebook installs the wireless chip `super_cool_wireless_component`,
  the corresponding number of `wireless_field` is 0.  `dram_field` above is
  more tricky, 0 means two 4G ram being installed on the Chromebook; 1 means
  two 8G ram being installed on the Chromebook.  If the probed results tell
  us that one 4G and one 8G rams are installed, the program will fail to
  generate the HWID identity because the combination of dram doesn't meet
  any case.

  A number respresents to a combination of a set of components, and it's even
  okey to be a set of different class of components like `firmware_field` in
  above example.  But for each class of components, it should belong to one
  `encoded_field`.  For example, below `encoded_fields` is invalid:

  ```yaml
  encoded_fields:
    aaa_field:
      0:
        class1: comp1
    bbb_field:
      0:
        class1: comp2
      1:
        class1: comp3
  ```

  The relationship between the encoded fields and the classes of components
  should form a `one-to-multi` mapping.

  Properties:
    _fields: A dictionary maps the encoded field name to the component
        combinations, which maps the encode index to a component combination.
        The component combination is a dictionary which maps the component
        class name to a list of component names.
    _field_to_comp_classes: A dictionary maps the encoded field name to a set
        of component class.
    _can_encode: True if this part works for encoding a BOM to the HWID string.
        Somehow there are some old, existed HWID databases which has an encoded
        field which maps two different indexes into exactly same component
        combinations.  In above case the database still works for decoding,
        but not encoding.
  """

  _SCHEMA = schema.Dict(
      'encoded fields',
      key_type=schema.Scalar('field name', str),
      value_type=schema.Dict(
          'encoded field',
          key_type=schema.Scalar(
              'index number', int,
              range(1024)),  # range(1024) is just a big enough range to denote
                             # that index numbers are non-negative integers.
          value_type=schema.Dict(
              'components',
              key_type=schema.Scalar('component class', str),
              value_type=schema.AnyOf([
                  schema.Scalar('empty list', type(None)),
                  schema.Scalar('component name', str),
                  schema.List(
                      'list of component name',
                      element_type=schema.Scalar('component name', str))])),
          min_size=1))

  def __init__(self, encoded_fields_expr):
    """Constructor.

    This constructor shouldn't be called by other modules.
    """
    self._SCHEMA.Validate(encoded_fields_expr)

    # Verify the input by constructing the encoded fields from scratch
    # because all checks are implemented in the manipulaping methods.
    self._fields = yaml.Dict()
    self._field_to_comp_classes = {}
    self._can_encode = True

    for field_name, field_data in encoded_fields_expr.iteritems():
      self._RegisterNewEmptyField(field_name, field_data.values()[0].keys())
      for index, comps in field_data.iteritems():
        comps = yaml.Dict([(c, self._StandardlizeList(n))
                           for c, n in comps.iteritems()])
        self.AddFieldComponents(field_name, comps, _index=index)

    # Preserve the class type reported by the parser.
    self._fields = copy.deepcopy(encoded_fields_expr)

  def __eq__(self, rhs):
    return isinstance(rhs, EncodedFields) and self._fields == rhs._fields

  def __ne__(self, rhs):
    return not self == rhs

  @property
  def can_encode(self):
    return self._can_encode

  def Export(self):
    """Exports to a dictionary so that it can be stored to the database file."""
    return self._fields

  @property
  def encoded_fields(self):
    """Returns a list of encoded field names."""
    return self._fields.keys()

  def GetField(self, field_name):
    """Gets the specific field.

    Args:
      field_name: A string of the name of the encoded field.

    Returns:
      A dictionary which maps each index number to the corresponding components
          combination (i.e. A dictionary of component class to a list of
          component names).
    """
    if field_name not in self._fields:
      raise common.HWIDException('The field name %r is invalid.' % field_name)

    ret = {}
    for index, comps in self._fields[field_name].iteritems():
      ret[index] = {c: self._StandardlizeList(n) for c, n in comps.iteritems()}
    return ret

  def GetComponentClasses(self, field_name):
    """Gets the related component classes of a specific field.

    Args:
      field_name: A string of th name of the encoded field.

    Returns:
      A set of string of component classes.
    """
    if field_name not in self._fields:
      raise common.HWIDException('The field name %r is invalid.' % field_name)

    return self._field_to_comp_classes[field_name]

  def GetFieldForComponent(self, comp_cls):
    """Gets the field which encodes the specific component class.

    Args:
      comp_cls: A string of the component class.

    Returns:
      None if no field for that; otherwise a string of the field name.
    """
    for field_name, comp_cls_set in self._field_to_comp_classes.iteritems():
      if comp_cls in comp_cls_set:
        return field_name
    return None

  def AddFieldComponents(self, field_name, components, _index=None):
    """Adds components combination to an existing encoded field.

    Args:
      field_name: A string of the name of the new encoded field.
      components: A dictionary which maps the component class to a list of
          component name.
      _index: Specify the index for the new component combination.
    """
    if field_name not in self._fields:
      raise common.HWIDException(
          'Encoded field %r does not exist' % (field_name,))

    if field_name == 'region_field':
      if len(components) != 1 or components.keys() != ['region']:
        raise common.HWIDException(
            'Region field should contain only region component.')

    if set(components.keys()) != self._field_to_comp_classes[field_name]:
      raise common.HWIDException('Each encoded field should encode a fixed set '
                                 'of component classes.')

    counters = {c: collections.Counter(n) for c, n in components.iteritems()}
    for existing_index, existing_comps in self.GetField(field_name).iteritems():
      if all(counter == collections.Counter(existing_comps[comp_cls])
             for comp_cls, counter in counters.iteritems()):
        self._can_encode = False
        logging.warning(
            'The components combination %r already exists (at index %r).',
            components, existing_index)

    index = (_index if _index is not None
             else max(self._fields[field_name].keys() or [-1]) + 1)
    self._fields[field_name][index] = yaml.Dict(
        sorted([(c, self._SimplifyList(n)) for c, n in components.iteritems()]))

  def AddNewField(self, field_name, components):
    """Adds a new field.

    Args:
      field_name: A string of the name of the new field.
      components: A dictionary which maps the component class to a list of
          component name.
    """
    if field_name in self._fields:
      raise common.HWIDException(
          'Encoded field %r already exists' % (field_name,))

    if field_name == 'region_field' or 'region' in components:
      raise common.HWIDException(
          'Region field should always exist in the HWID database, it is '
          'prohibited to add a new field called "region_field".')

    self._RegisterNewEmptyField(field_name, components.keys())

    self.AddFieldComponents(field_name, components)

  def _RegisterNewEmptyField(self, field_name, comp_classes):
    if not comp_classes:
      raise common.HWIDException(
          'An encoded field must includes at least one component class.')

    self._fields[field_name] = yaml.Dict()
    self._field_to_comp_classes[field_name] = set(comp_classes)

  @classmethod
  def _SimplifyList(cls, data):
    if not data:
      return None
    elif len(data) == 1:
      return data[0]
    else:
      return sorted(data)

  @classmethod
  def _StandardlizeList(cls, data):
    return sorted(type_utils.MakeList(data)) if data is not None else []


class ComponentInfo(type_utils.Obj):
  def __init__(self, values, status):
    super(ComponentInfo, self).__init__(values=values, status=status)


class Components(object):
  """Class for holding `components` part in a HWID database.

  `components` part in a HWID database records information of all components
  which might be found on the device.

  In the HWID database file, `components` part looks like:

  ```yaml
  components:
    <comonent_class_1_name>:
      items:
        <component_name>:
          value: <a_dict_of_expected_probed_result_values>|null
          status: unsupported|deprecated|unqualified|supported
        <component_name>:
          value: <a_dict_of_expected_probed_result_values>
          status: unsupported|deprecated|unqualified|supported
        ...
    ...
  ```

  For example, it might look like:

  ```yaml
  components:
    battery:
      items:
        battery_small:
          status: deprecated
          values:
            tech: Battery Li-ion
            size: '2500000'
        battery_medium:
          status: unqualified
          values:
            tech: Battery Li-ion
            size: '123456789'

    cellular:
      items:
        cellular_default:
          values: null
        cellular_0:
          values:
            idVendor: 89ab
            idProduct: abcd
            name: Cellular Card
  ```

  In above example, when we probe the battery of the device, if the probed
  result values contains {'tech': 'Battery Li-ion', size: '123456789'}, we
  consider as there's a component named "battery_small" installed on the device.

  A special case is "value: null", this means the component is a
  "default component".  In early build, sometime maybe the driver is not ready
  so we have to set a default component to mark that those device actually
  have the component.

  Valid status are: supported, unqualified, deprecated and unsupported.  Each
  value has its own meaning:
    * supported: This component is currently being used to build new units and
          allowed to be used in later build (PVT and later).
    * unqualified: The component is acceptable to be installed on the device in
          early normal build (before PVT, not included).
    * deprecated: This component is no longer being used to build new units,
          but is supported in RMA process.
    * unsupported: This component is not allowed to be used to build new units,
          and is not supported in RMA process.
  If not specified, status defaults to supported.

  After probing all kind of components, it results in a BOM list, which records
  a list of names of the installed components.  Then we generate the HWID
  encoded string by looking up the encoded fields to transfer the BOM list
  into numbers and union them.

  Attributes:
    _components: A dictionary which maps the component class name to a list
        of ComponentInfo object.
    _can_encode: True if the original data doesn't contain legacy information
        so that the whole database works for encoding a BOM to the HWID string.
        As the idea of non-probeable components are deprecated and the idea of
        default components are approached by rules, the HWID database contains
        non-probeable or default components will be mark as _can_encode=False.
    _default_comonents: A set of default components.
    _non_probeable_component_classes: A set of name of the non-probeable
        component class.
  """
  _SCHEMA = schema.Dict(
      'components',
      key_type=schema.Scalar('component class', str),
      value_type=schema.FixedDict(
          'component description',
          items={
              'items': schema.Dict(
                  'components',
                  key_type=schema.Scalar('component name', str),
                  value_type=schema.FixedDict(
                      'component attributes',
                      items={
                          'values': schema.AnyOf([
                              schema.Dict(
                                  'probed key-value pairs',
                                  key_type=schema.Scalar('probed key', str),
                                  value_type=schema.AnyOf([
                                      schema.Scalar('probed value', str),
                                      schema.Scalar(
                                          'probde value regex', Value)]),
                                  min_size=1),
                              schema.Scalar('none', type(None))])},
                      optional_items={
                          'default': schema.Scalar(
                              'is default component item (deprecated)', bool),
                          'status': schema.Scalar(
                              'item status', str,
                              choices=common.COMPONENT_STATUS)}))},
          optional_items={
              'probeable': schema.Scalar(
                  'is component probeable (deprecate)', bool)}))

  _DUMMY_KEY = 'dummy_probed_value_key'

  def __init__(self, components_expr):
    """Constructor.

    This constructor shouldn't be called by other modules.
    """
    self._SCHEMA.Validate(components_expr)

    self._components_expr = copy.deepcopy(components_expr)
    self._components = {}

    self._can_encode = True
    self._default_components = set()
    self._non_probeable_component_classes = set()

    for comp_cls, comps_data in self._components_expr.iteritems():
      self._components[comp_cls] = {}
      for comp_name, comp_attr in comps_data['items'].iteritems():
        self._AddComponent(comp_cls, comp_name, comp_attr['values'],
                           comp_attr.get('status',
                                         common.COMPONENT_STATUS.supported))

        if comp_attr.get('default') is True:
          # We now use "values: null" to indicate a default component and
          # ignore the "default: True" field.
          self._default_components.add((comp_cls, comp_name))

      if comps_data.get('probeable') is False:
        logging.info(
            'Found non-probeable component class %r, mark can_encode=False.',
            comp_cls)
        self._can_encode = False
        self._non_probeable_component_classes.add(comp_cls)

  def __eq__(self, rhs):
    # pylint: disable=protected-access
    return isinstance(rhs, Components) and self._components == rhs._components

  def __ne__(self, rhs):
    return not self == rhs

  def Export(self):
    """Exports into a serializable dictionary which can be stored into a HWID
    database file."""
    # Apply the changes back to the original data for YAML, either adding a new
    # component or updating the component status.
    for comp_cls in self.component_classes:
      components_dict = self._components_expr.setdefault(
          comp_cls, {'items': yaml.Dict()})['items']
      for comp_name, comp_info in self.GetComponents(comp_cls).iteritems():
        if comp_name not in components_dict:
          components_dict[comp_name] = yaml.Dict()
          if comp_info.status != common.COMPONENT_STATUS.supported:
            components_dict[comp_name]['status'] = comp_info.status
          components_dict[comp_name]['values'] = comp_info.values

        else:
          if comp_info.status != components_dict[comp_name].get(
              'status', common.COMPONENT_STATUS.supported):
            if comp_info.status == common.COMPONENT_STATUS.supported:
              del components_dict[comp_name]['status']
            else:
              components_dict[comp_name]['status'] = comp_info.status

    return self._components_expr

  @property
  def can_encode(self):
    """Returns true if the components is not the legacy one which let the whole
    database unable to encode the BOM."""
    return self._can_encode

  @property
  def component_classes(self):
    """Returns a list of string of the component class names."""
    return self._components.keys()

  def GetComponents(self, comp_cls):
    """Gets the components of the specific component class.

    Args:
      comp_cls: A string of the name of the component class.

    Returns:
      A dict which maps a string of component name to a `ComponentInfo` object,
      which is a named tuple contains two attributes:
        values: A string-to-string dict of expected probed results.
        status: One of "unsupported", "deprecated", "unqualified", "supported".
    """
    return self._components.get(comp_cls, {})

  def GetDefaultComponent(self, comp_cls):
    """Gets the default components of the specific component class if exists.

    Args:
      comp_cls: A string of the name of the component class.

    Returns:
      None or a string of the component name.
    """
    for comp_name, comp_info in self._components.get(comp_cls, {}).iteritems():
      if comp_info.values is None:
        return comp_name

  def AddComponent(self, comp_cls, comp_name, values, status):
    """Adds a new component.

    Args:
      comp_cls: A string of the component class.
      comp_name: A string of the name of the component.
      values: A dict of the expected probed results.
      status: The component status, one of "unsupported", "deprecated",
          "unqualified", "supported".
    """
    if comp_cls == 'region':
      raise common.HWIDException('Region component class is not modifiable.')

    self._AddComponent(comp_cls, comp_name, values, status)

  def SetComponentStatus(self, comp_cls, comp_name, status):
    """Sets the status of a specific component.

    Args:
      comp_cls: The component class name.
      comp_name: The component name.
      status: The component status, one of "unsupported", "deprecated",
          "unqualified", "supported".
    """
    if comp_cls == 'region':
      raise common.HWIDException('Region component class is not modifiable.')

    self._SCHEMA.value_type.items[
        'items'].value_type.optional_items['status'].Validate(status)

    if comp_name not in self._components.get(comp_cls, {}):
      raise common.HWIDException('Component (%r, %r) is not recorded.' %
                                 (comp_cls, comp_name))

    self._components[comp_cls][comp_name].status = status

  def _AddComponent(self, comp_cls, comp_name, values, status):
    def _IsSubDict(super_dict, sub_dict):
      if super_dict is None or sub_dict is None:
        return False
      if set(sub_dict.keys()) - set(super_dict.keys()):
        return False
      for k, v in sub_dict.iteritems():
        if super_dict[k] != v:
          return False
      return True

    self._SCHEMA.value_type.items[
        'items'].value_type.items['values'].Validate(values)
    self._SCHEMA.value_type.items[
        'items'].value_type.optional_items['status'].Validate(status)

    if comp_name in self.GetComponents(comp_cls):
      raise common.HWIDException('Component (%r, %r) already exists.' %
                                 (comp_cls, comp_name))

    if values is None and any(
        c.values is None for c in self.GetComponents(comp_cls).itervalues()):
      logging.warning('Found more than one default component of %r, '
                      'mark can_encode=False.', comp_cls)
      self._can_encode = False

    for existed_comp_name, existed_comp_info in self.GetComponents(
        comp_cls).iteritems():
      existed_comp_values = existed_comp_info.values
      if values == existed_comp_values:
        logging.warning('Probed values %r is ambiguous with %r',
                        values, existed_comp_name)
        self._can_encode = False

    self._components.setdefault(comp_cls, yaml.Dict())
    self._components[comp_cls][comp_name] = ComponentInfo(values, status)


_PatternDatum = collections.namedtuple('_PatternDatum',
                                       ['encoding_scheme', 'fields'])
_PatternField = collections.namedtuple('_PatternField', ['name', 'bit_length'])
class Pattern(object):
  """A class for parsing and obtaining information of a pre-defined encoding
  pattern.

  The `pattern` part of a HWID database records a list of patterns.  Each
  pattern records:
    1. `image_ids`: A list of image id for this pattern.  When we are decoding
       a HWID identity, we will use the pattern which `image_ids` field
       includes the image id in the HWID identity.
    2. `encoding_scheme`: Either "base32" or "base8192".  This is the name of
       the algorithm to encoding/decoding the binary string.
    3. `fields`: Bit positions of each type of components.  Since the hardware
       component might be added into the HWID database in anytime and we can
       only append extra bits to the components bitset at the end so that
       old HWID identity can be decoded by the same pattern, the index number
       of the installed component might have to be splitted into multiple part
       when we union all numbers into a big binary string.  For example, if the
       `fields` defines:

       ```yaml
       - battery: 2
       - cpu: 1
       - battery 3
       ```

       Then the first 2 bits of the components bitset are the least 2 bits of
       the index of the battery.  The 4~6 bits of the components bitset are the
       3~5 bits of the index of the battery.  Here is the corresponding mapping
       between the components bitset and the index of the battery of above
       example.  (note that the bit for cpu is marked as "?" because it is not
       related to the battery.)

         bitset  battery_index    bitset  battery_index
         00?000  0                00?100  16
         01?000  1                01?100  17
         10?000  2                10?100  18
         11?000  3                11?100  19
         00?001  4                00?101  20
         01?001  5                01?101  21
         10?001  6                10?101  22
         11?001  7                11?101  23
         00?010  8                00?110  24
         01?010  9                01?110  25
         10?010  10               10?110  26
         11?010  11               11?110  27
         00?011  12               00?111  28
         01?011  13               01?111  29
         10?011  14               10?111  30
         11?011  15               11?111  31

  The format of `pattern` part in the HWID database file is:

  ```yaml
  pattern:
  - image_ids: <a_list_of_image_ids>
  - encoding_scheme: <base32_or_base8192>
  - fields:
    - <component_class_name>: <number_of_bits>
    - <component_class_name>: <number_of_bits>
    ...

  - image_ids: <a_list_of_image_ids>
  - encoding_scheme: <base32_or_base8192>
  - fields:
    - <component_class_name>: <number_of_bits>
    - <component_class_name>: <number_of_bits>
    ...
  ...

  ```

  """

  _SCHEMA = schema.List(
      'pattern list',
      element_type=schema.FixedDict(
          'pattern',
          items={
              'image_ids': schema.List(
                  'image ids',
                  element_type=schema.Scalar(
                      'image id', int, choices=ImageId.NUMBER_RANGE),
                  min_length=1),
              'encoding_scheme': schema.Scalar(
                  'encoding scheme', str, choices=['base32', 'base8192']),
              'fields': schema.List(
                  'encoded fields',
                  schema.Dict(
                      'pattern field',
                      key_type=schema.Scalar('encoded index', str),
                      value_type=schema.Scalar('bit offset', int, range(128)),
                      min_size=1,
                      max_size=1))}),
      min_length=1)

  def __init__(self, pattern_list_expr):
    """Constructor.

    This constructor shouldn't be called by other modules.
    """
    self._SCHEMA.Validate(pattern_list_expr)

    self._image_id_to_pattern = {}

    for pattern_expr in pattern_list_expr:
      pattern_obj = _PatternDatum(pattern_expr['encoding_scheme'], [])
      for field_expr in pattern_expr['fields']:
        pattern_obj.fields.append(
            _PatternField(field_expr.keys()[0], field_expr.values()[0]))

      for image_id in pattern_expr['image_ids']:
        if image_id in self._image_id_to_pattern:
          raise common.HWIDException(
              'One image id should map to one pattern, but image id %r maps to '
              'multiple patterns.' % image_id)

        self._image_id_to_pattern[image_id] = pattern_obj

  def __eq__(self, rhs):
    # pylint: disable=protected-access
    return (isinstance(rhs, Pattern) and
            self._image_id_to_pattern == rhs._image_id_to_pattern)

  def __ne__(self, rhs):
    return not self == rhs

  def Export(self):
    """Exports this `pattern` part of HWID database into a serializable object
    which can be stored into a HWID database file."""
    pattern_list = []
    for image_id, pattern in sorted(self._image_id_to_pattern.iteritems()):
      for obj_to_export, existed_pattern in pattern_list:
        if pattern is existed_pattern:
          obj_to_export['image_ids'].append(image_id)
          break
      else:
        obj_to_export = yaml.Dict([
            ('image_ids', [image_id]),
            ('encoding_scheme', pattern.encoding_scheme),
            ('fields', [{field.name: field.bit_length}
                        for field in pattern.fields])])
        pattern_list.append((obj_to_export, pattern))

    return [pattern for pattern, _ in pattern_list]

  @property
  def all_image_ids(self):
    """Returns all image ids."""
    return self._image_id_to_pattern.keys()

  def AddEmptyPattern(self, image_id, encoding_scheme):
    """Adds a new empty pattern.

    Args:
      image_id: The image id of the new pattern.
      encoding_sheme: The encoding scheme of the new pattern.
    """
    self._SCHEMA.element_type.items['image_ids'].element_type.Validate(image_id)
    self._SCHEMA.element_type.items['encoding_scheme'].Validate(encoding_scheme)

    if image_id in self._image_id_to_pattern:
      raise common.HWIDException(
          'The image id %r is already in used.' % image_id)

    self._image_id_to_pattern[image_id] = _PatternDatum(encoding_scheme, [])

  def AddImageId(self, reference_image_id, image_id):
    """Adds an image id to a pattern by the specific image id.

    Args:
      reference_image_id: An integer of the image id.  If not given, the latest
          image id would be used.
      image_id: The image id to be added.
    """
    self._SCHEMA.element_type.items['image_ids'].element_type.Validate(image_id)

    if image_id in self._image_id_to_pattern:
      raise common.HWIDException(
          'The image id %r has already been in used.' % image_id)

    self._image_id_to_pattern[image_id] = self._GetPattern(reference_image_id)

  def AppendField(self, field_name, bit_length, image_id=None):
    """Append a field to the pattern.

    Args:
      field_name: Name of the field.
      bit_length: Bit width to add.
      image_id: An integer of the image id. If not given, the latest image id
          would be used.
    """
    self._SCHEMA.element_type.items[
        'fields'].element_type.key_type.Validate(field_name)
    self._SCHEMA.element_type.items[
        'fields'].element_type.value_type.Validate(bit_length)

    self._GetPattern(image_id).fields.append(
        _PatternField(field_name, bit_length))

  def GetEncodingScheme(self, image_id=None):
    """Gets the encoding scheme recorded in the pattern.

    Args:
      image_id: An integer of the image id to query. If not given, the latest
          image id would be used.

    Returns:
      Either "base32" or "base8192".
    """
    return self._GetPattern(image_id).encoding_scheme

  def GetTotalBitLength(self, image_id=None):
    """Gets the total bit length defined by the pattern.

    Args:
      image_id: An integer of the image id to query. If not given, the latest
          image id would be used.

    Returns:
      A int indicating the total bit length.
    """
    return sum([field.bit_length
                for field in self._GetPattern(image_id).fields])

  def GetFieldsBitLength(self, image_id=None):
    """Gets a map for the bit length of each encoded fields defined by the
    pattern. Scattered fields with the same field name are aggregated into one.

    Args:
      image_id: An integer of the image id to query. If not given, the latest
          image id would be used.

    Returns:
      A dict mapping each encoded field to its bit length.
    """
    ret = collections.defaultdict(int)
    for field in self._GetPattern(image_id).fields:
      ret[field.name] += field.bit_length
    return dict(ret)

  def GetBitMapping(self, image_id=None, max_bit_length=None):
    """Gets a list indicating the mapping target (field name and the offset) of
    each bit in the components bitset.

    For example, the returned map may say that bit 5 in the components bitset
    corresponds to the least significant bit of encoded field 'cpu'.

    Args:
      image_id: An integer of the image id to query. If not given, the latest
          image id would be used.

      max_bit_length: The max length of the return list.  If given, it is used
          to check against the encoding pattern to see if there is an incomplete
          bit chunk.

    Returns:
      A list of BitEntry objects indexed by bit position in the compoents
          bitset.  Each BitEntry object has attributes (field, bit_offset)
          indicating which bit_offset of field this particular bit corresponds
          to. For example, if ret[6] has attributes (field='cpu', bit_offset=1),
          then it means that bit position 6 of the binary string corresponds
          to the bit offset 1 (which is the second least significant bit)
          of encoded field 'cpu'.
    """
    BitEntry = collections.namedtuple('BitEntry', ['field', 'bit_offset'])

    total_bit_length = self.GetTotalBitLength(image_id=image_id)
    if max_bit_length is None:
      max_bit_length = total_bit_length
    else:
      max_bit_length = min(max_bit_length, total_bit_length)

    ret = []
    field_offset_map = collections.defaultdict(int)
    for name, bit_length in self._GetPattern(image_id).fields:
      # Normally when one wants to extend bit length of a field, one should
      # append new pattern field instead of expanding the last field.
      # However, for some project, we already have cases where last pattern
      # fields were expanded directly. See crosbug.com/p/30266.
      #
      # Ignore extra bits if we have reached `max_bit_length` so that we can
      # generate the correct bit mapping in previous versions whose total
      # bit length is smaller.
      remaining_length = max_bit_length - len(ret)
      if remaining_length <= 0:
        break
      real_length = min(bit_length, remaining_length)

      # Big endian.
      for offset_delta in xrange(real_length - 1, -1, -1):
        ret.append(BitEntry(name, offset_delta + field_offset_map[name]))

      field_offset_map[name] += real_length

    return ret

  def _GetPattern(self, image_id=None):
    """Get the pattern by a given image id.

    Args:
      image_id: An integer of the image id to query.  If not given, the latest
          image id would be used.

    Returns:
      The `_PatternDatum` object.
    """
    if image_id is None:
      return self._image_id_to_pattern[self._max_image_id]

    if image_id not in self._image_id_to_pattern:
      raise common.HWIDException('No pattern for image id %r.' % image_id)

    return self._image_id_to_pattern[image_id]

  @property
  def _max_image_id(self):
    return ImageId.GetMaxImageIDFromList(self._image_id_to_pattern.keys())


class Rules(object):
  """A class for parsing rules defined in the database.

  The `rules` part of a HWID database consists of a list of rules to be
  evaluate.  There's two kind of rules:

    1. `device_info`: This kind of rules will be evaluated before encoding the
       BOM object into the HWID identity.  While generating the HWID identity,
       we probe the Chromebook to know what components are installed on the
       Chromebook and store the component list as a BOM object.  But since
       some unprobeable information is also needed to be encoded into The HWID
       identity (such as `image_id`), the BOM object is "incomplete".
       The `device_info` rules then will fill those unprobeable information into
       the BOM object so that it can be encoded into a HWID identity.
    2. `verify`: This kind of rules will be evaluated when we want to verify
       whether a HWID identity is valid (for example, after a HWID identity is
       generated).  Sometimes we might find that two specific hardware
       components living together would crash the Chromebook, then we have to
       avoid this combination.  That's one example of when to use the `verify`
       rules.  The `verify` rules allow developers to specify some customized
       verifying process.

  The format of `rules` part in the HWID database file is:

  ```
  rules:
  - name: <name>
    evaluate: <expressions>
    when: <when_expression>     # This field is optional.
    otherwise: <expressions>    # This field is optional.
  ...

  ```

  <name> can be any string starts with either "device_info." or "verify.".

  <expressions> can be a string of python expression, or a list of string of
  python expression, see below for detail descrption.

  <when_expression> is a string of python expression.

  `when:` field is optional, it is used for condition evaluating, the
  <expressions> specified in `evaluate:` field will be run only if the
  evaluated value of <when_expression> is true.

  `otherwise` field is also optional, but shouldn't exist if there's no `when:`
  field.  <expressions> specified in this field will be run if the evaluated
  value of <when_expression> is false.

  `cros.factory.hwid.v3.common_rule_functions` and
  `cros.factory.hwid.v3.hwid_rule_functions` packages have already defined a
  series of functions which can be called in <expressions>.

  An example of `rules` part in a HWID database is:
  ```
  rules:
  - name: device_info.set_image_id
    evaluate: SetImageId('PVT')

  - name: device_info.component.has_cellular
    when: GetDeviceInfo('component.has_cellular')
    evaluate: Assert(ComponentEq('cellular', 'foxconn_novatel'))
    otherwise: Assert(ComponentEq('cellular', None))

  - name: device_info.component.keyboard
    when: GetOperationMode() != 'rma'
    evaluate: >
        SetComponent(
            'keyboard', LookupMap(GetDeviceInfo('component.keyboard'), {
                'US_API': 'us_darfon',
                'UK_API': 'gb_darfon',
                'FR_API': 'fr_darfon',
                'DE_API': 'de_darfon',
                'SE_API': 'se_darfon',
                'NL_API': 'us_intl_darfon',
            }))

  - name: verify.vpd.ro
    evaluate:
    - Assert(ValidVPDValue('ro', 'serial_number'))
  ```

  Properties:
    rules: A list of Rule instances, which include both type of rules.
    device_info_rules: A list of `device_info` type of rules.
    verify_rules: A list of `verify` type of rules.

  """

  _RULE_TYPES = type_utils.Enum(['verify', 'device_info'])
  _EXPRESSIONS_SCHEMA = schema.AnyOf([
      schema.Scalar('rule expression', str),
      schema.List('list of rule expressions',
                  schema.Scalar('rule expression', str))])
  _RULE_SCHEMA = schema.FixedDict(
      'rule',
      items={'name': schema.Scalar('rule name', str),
             'evaluate': _EXPRESSIONS_SCHEMA},
      optional_items={'when': schema.Scalar('expression', str),
                      'otherwise': _EXPRESSIONS_SCHEMA})

  def __init__(self, rule_expr_list):
    """Constructor.

    This constructor shouldn't be called from other modules.
    """
    if not isinstance(rule_expr_list, list):
      raise common.HWIDException(
          '`rules` part of a HWID database should be a list, but got %r' %
          (rule_expr_list,))

    self._rules = []

    for rule_expr in rule_expr_list:
      self._RULE_SCHEMA.Validate(rule_expr)

      rule = Rule.CreateFromDict(rule_expr)
      if not any([rule.name.startswith(x + '.') for x in self._RULE_TYPES]):
        raise common.HWIDException(
            'Invalid rule name %r; rule name must be prefixed with '
            '"device_info." (evaluated when generating HWID) '
            'or "verify." (evaluated when verifying HWID)' % rule.name)

      self._rules.append(rule)

  def __eq__(self, rhs):
    # pylint: disable=protected-access
    return isinstance(rhs, Rules) and self._rules == rhs._rules

  def __ne__(self, rhs):
    return not self == rhs

  def Export(self):
    """Exports the `rule` part into a list of dictionary object which can be
    saved to the HWID database file."""
    def _TransToOrderedDict(rule_dict):
      ret = yaml.Dict([('name', rule_dict['name']),
                       ('evaluate', rule_dict['evaluate'])])
      for key in ['when', 'otherwise']:
        if key in rule_dict:
          ret[key] = rule_dict[key]
      return ret
    return [_TransToOrderedDict(rule.ExportToDict()) for rule in self._rules]

  @property
  def device_info_rules(self):
    return self._GetRules(self._RULE_TYPES.device_info + '.')

  @property
  def verify_rules(self):
    return self._GetRules(self._RULE_TYPES.verify + '.')

  def AddDeviceInfoRule(self, name_suffix, evaluate, **kwargs):
    """Adds a device info type rule.

    Args:
      name_suffix: A string of the suffix of the rule name, the actual rule name
          will be "device_info.<name_suffix>".
      **kwargs:
        position:  None to append the rule at the end of all rules; otherwise
          if the value is N, the rule will be inserted right before the N-th
          device_info rule.
        other arguments: Arguments needed by the Rule class' constructor.
      position:
    """
    position = kwargs.pop('position', None)
    self._AddRule(self._RULE_TYPES.device_info, position, name_suffix,
                  evaluate, **kwargs)

  def _GetRules(self, prefix):
    return [rule for rule in self._rules if rule.name.startswith(prefix)]

  def _AddRule(self, rule_type, position, name_suffix, evaluate, **kwargs):
    rule_obj = Rule(rule_type + '.' + name_suffix, evaluate, **kwargs)

    if position is not None:
      order = -1
      for index, existed_rule_obj in enumerate(self._rules):
        if not existed_rule_obj.name.startswith(rule_type):
          continue
        order += 1
        if order == position:
          self._rules.insert(index, rule_obj)
          return

    self._rules.append(rule_obj)
