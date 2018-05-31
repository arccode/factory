# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from collections import OrderedDict
import itertools
import logging
import math
import re
import uuid

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import probe
from cros.factory.hwid.v3 import yaml_wrapper as yaml


# The components that are always be created at the front of the pattern,
# even if they don't exist in the probe results.
ESSENTIAL_COMPS = [
    'mainboard',
    'region',
    'chassis',
    'cpu',
    'storage',
    'dram']

# The components that are added in order if they exist in the probe results.
PRIORITY_COMPS = OrderedDict([
    ('firmware_keys', 3),
    ('ro_main_firmware', 3),
    ('ro_ec_firmware', 2)])


def FilterSpecialCharacter(string):
  """Filters special cases and converts all seperation characters to underlines.
  """
  string = re.sub(r'[: .-]+', '_', string)
  string = re.sub(r'[^A-Za-z0-9_]+', '', string)
  string = re.sub(r'[_]+', '_', string)
  string = re.sub(r'^_|_$', '', string)
  if not string:
    string = 'unknown'
  return string


def DetermineComponentName(comp_cls, value, name_list=None):
  comp_name = _DetermineComponentName(comp_cls, value)
  if name_list is None:
    name_list = []
  return HandleCollisionName(comp_name, name_list)


def HandleCollisionName(comp_name, name_list):
  # To prevent name collision, add "_n" if the name already exists.
  if name_list is None:
    name_list = []
  if comp_name in name_list:
    suffix_num = 1
    while '%s_%d' % (comp_name, suffix_num) in name_list:
      suffix_num += 1
    comp_name = '%s_%d' % (comp_name, suffix_num)
  return comp_name


def _DetermineComponentName(comp_cls, value):
  """Determines the componenet name by the value.

  For some specific components, we can determine a meaningful name by the
  component value. For example the value contains the vendor name, or the part
  number. But some components value don't, so we just use UUID.
  Note that the function doen't ganrantee the name is deterministic and unique.

  Args:
    comp_cls: the component class name.
    value: the probed value of the component item.

  Returns:
    the component name.
  """
  # Known specific components.
  if comp_cls == 'firmware_keys':
    if 'devkeys' in value['key_root']:
      return 'firmware_keys_dev'
    else:
      return 'firmware_keys_non_dev'

  # General components.
  if len(value) == 1:
    return FilterSpecialCharacter(str(value.values()[0]))
  try:
    return '%s_%smb_%s' % (value['part'], value['size'], value['slot'])
  except KeyError:
    pass
  for key in ['id', 'version', 'model', 'manufacturer', 'part', 'name',
              'compact_str']:
    if key in value:
      return FilterSpecialCharacter(str(value[key]))
  return comp_cls + '_' + str(uuid.uuid4())[:8]


def PromptAndAsk(question_str, default_answer=True):
  """Prompts the question and asks user to decide yes or no.

  If the first character user enter is not 'y' nor 'n', the method returns the
  default answer.

  Args:
    question_str: the question prompted to ask the user.
    default_answer: the default answer of the question.
  """
  hint_str = ' [Y/n] ' if default_answer else ' [y/N] '
  input_str = raw_input(question_str + hint_str)
  if input_str and input_str[0].lower() in ['y', 'n']:
    ret = input_str[0].lower() == 'y'
  else:
    ret = default_answer
  logging.info('You chose: %s', 'Yes' if ret else 'No')
  return ret


def ChecksumUpdater():
  """Finds the checksum updater in the chromium source tree.

  Returns:
    a update_checksum module if found. otherwise return None.
  """
  try:
    from cros.chromeoshwid import update_checksum
    return update_checksum
  except ImportError:
    logging.error('checksum_update is not found.')
    return None


class DatabaseBuilder(object):
  """A helper class for updating a HWID Database object.

  properties:
    database: The Database object this class manipulates on.
    _from_empty_database: True if this builder is for creating a new database.
  """

  _DEFAULT_COMPONENT_SUFFIX = '_default'

  def __init__(self, database_path=None, project=None, image_name=None):
    """Constructor.

    If the `database_path` is given, this class will load the existed database;
    otherwise this class will create an new empty database which project and
    the image name of image id 0 meets the given arguments `project` and
    `image_name`.

    Args:
      database_path: A path to the database to be loaded.
      project: A string of the project name.
      image_name: A string of the default image name.
    """
    if database_path:
      self.database = Database.LoadFile(database_path, verify_checksum=False)
      self._from_empty_database = False
      if not self.database.can_encode:
        raise ValueError('The given HWID database %r is legacy and not '
                         'supported by DatabaseBuilder.' % database_path)
    else:
      if project is None or image_name is None:
        raise ValueError('No project name.')
      self.database = self._BuildEmptyDatabase(project.upper(), image_name)
      self._from_empty_database = True

  def AddDefaultComponent(self, comp_cls):
    """Adds a default component item and corresponding rule to the database.

    Args:
      comp_cls: The component class.
    """
    logging.info('Component [%s]: add a default item.', comp_cls)

    if self.database.GetDefaultComponent(comp_cls) is not None:
      raise ValueError(
          'The component class %r already has a default component.' % comp_cls)

    comp_name = comp_cls + self._DEFAULT_COMPONENT_SUFFIX
    self.database.AddComponent(
        comp_cls, comp_name, None, common.COMPONENT_STATUS.unqualified)

  def AddNullComponent(self, comp_cls):
    """Updates the database to be able to encode a device without specific
    component class.

    Args:
      comp_cls: A string of the component class name.
    """
    field_name = self.database.GetEncodedFieldForComponent(comp_cls)
    if not field_name:
      self._AddNewEncodedField(comp_cls, [])
      return

    if len(self.database.GetComponentClasses(field_name)) > 1:
      raise ValueError(
          'The encoded field %r for component %r encodes more than one '
          'component class so it\'s not trivial to mark a null %r component.  '
          'Please update the database by a real probed results.' %
          (field_name, comp_cls, comp_cls))
    if all(comps[comp_cls]
           for comps in self.database.GetEncodedField(field_name).itervalues()):
      self.database.AddEncodedFieldComponents(field_name, {comp_cls: []})

  def UpdateByProbedResults(self, probed_results, device_info, vpd,
                            image_name=None):
    """Updates the database by a real probed results.

    Args:
      probed_results: The probed result obtained by probing the device.
      device_info: An emty dict or a dict contains the device information.
      vpd: An empty dict or a dict contains the vpd values.
    """
    if self._from_empty_database and image_name:
      logging.warning('The argument `image_name` will be ignored when '
                      'DatabaseBuilder is creating the new database instead of '
                      'updating an existed database.')

    bom = self._UpdateComponents(probed_results, device_info, vpd)
    self._UpdateEncodedFields(bom)
    if not self._from_empty_database:
      self._MayAddNewPatternAndImage(image_name)
    self._UpdatePattern()

  def Render(self, database_path):
    """Renders the database to a yaml file.

    Args:
      database_path: the path of the output HWID database file.
    """
    self.database.DumpFile(database_path)

    checksum_updater = ChecksumUpdater()
    if checksum_updater is None:
      logging.info('Checksum is not updated.')
    else:
      logging.info('Update the checksum.')
      checksum_updater.UpdateFile(database_path)

  @classmethod
  def _BuildEmptyDatabase(cls, project, image_name):
    return Database.LoadData(
        'checksum: None\n' +
        'project: %s\n' % project +
        'encoding_patterns:\n' +
        '  0: default\n' +
        'image_id:\n' +
        '  0: %s\n' % image_name +
        'pattern:\n' +
        '  - image_ids: [0]\n' +
        '    encoding_scheme: %s\n' % common.ENCODING_SCHEME.base8192 +
        '    fields: []\n' +
        'encoded_fields:\n' +
        '  region_field: !region_field []\n' +
        'components:\n' +
        '  region: !region_component\n' +
        'rules: []\n')

  def _AddComponent(self, comp_cls, probed_value):
    """Tries to add a item into the component.

    Args:
      comp_cls: The component class.
      probed_value: The probed value of the component.
    """
    # Set old firmware components to deprecated.
    if comp_cls in ['ro_main_firmware', 'ro_ec_firmware', 'ro_pd_firmware']:
      for comp_name in self.database.GetComponents(comp_cls):
        self.database.SetComponentStatus(
            comp_cls, comp_name, common.COMPONENT_STATUS.deprecated)

    comp_name = DetermineComponentName(
        comp_cls, probed_value, self.database.GetComponents(comp_cls).keys())

    logging.info('Component %s: add an item "%s".', comp_cls, comp_name)
    self.database.AddComponent(
        comp_cls, comp_name, probed_value, common.COMPONENT_STATUS.unqualified)

    # Deprecate the default component.
    default_comp_name = self.database.GetDefaultComponent(comp_cls)
    if default_comp_name is not None:
      self.database.SetComponentStatus(
          comp_cls, default_comp_name, common.COMPONENT_STATUS.unsupported)

  def _AddComponents(self, comp_cls, probed_values):
    """Adds a list of components to the database.

    Args:
      comp_cls: A string of the component class name.
      probed_values: A list of probed value from the device.
    """
    def _IsSubset(subset, superset):
      return all([subset.get(key) == value
                  for key, value in superset.iteritems()])

    # Only add the unique component to the database.
    # For example, if the given probed values are
    #   {"a": "A", "b": "B"},
    #   {"a": "A", "b": "B", "c": "C"},
    #   {"a": "A", "x": "X", "y": "Y"}
    # then we only add the first and the third components because the second
    # one is considered as the same as the first one.
    for i, probed_value_i in enumerate(probed_values):
      if (any(_IsSubset(probed_value_i, probed_values[j]) and
              probed_value_i != probed_values[j] for j in xrange(i)) or
          any(_IsSubset(probed_value_i, probed_values[j])
              for j in xrange(i + 1, len(probed_values)))):
        continue
      self._AddComponent(comp_cls, probed_value_i)

  def _AddNewEncodedField(self, comp_cls, comp_names):
    """Adds a new encoded field for the specific component class.

    Args:
      comp_cls: The component class.
      comp_names: A list of component name.
    """
    field_name = HandleCollisionName(
        comp_cls + '_field', self.database.encoded_fields)
    self.database.AddNewEncodedField(field_name, {comp_cls: comp_names})

  def _UpdateComponents(self, probed_results, device_info, vpd):
    """Updates the component part of the database.

    This function update the database by trying to generate the BOM object
    and add mis-matched components on the probed results to the database.

    Args:
      probed_results: The probed results generated by probing the device.
      device_info: The device info object.
      vpd: A dict stores the vpd values.
    """
    # Add extra components.
    existed_comp_classes = self.database.GetComponentClasses()
    for comp_cls, probed_comps in probed_results.iteritems():
      if comp_cls not in existed_comp_classes:
        # We only need the probe values here.
        probed_values = [probed_comp['values'] for probed_comp in probed_comps]
        if not probed_values:
          continue

        self._AddComponents(comp_cls, probed_values)

        if self._from_empty_database:
          continue

        add_null = PromptAndAsk(
            'Found probed values of [%s] component\n' % comp_cls +
            ''.join(['\n' + yaml.dump(probed_value, default_flow_style=False)
                     for probed_value in probed_values]).replace('\n', '\n  ') +
            '\n' +
            'to be added to the database, please confirm that:\n' +
            'If the device has a SKU without %s component, ' % comp_cls +
            'please enter "Y".\n' +
            'If the device always has %s component, ' % comp_cls +
            'please enter "N".\n',
            default_answer=True)

        if add_null:
          self.AddNullComponent(comp_cls)

    # Add mismatched components to the database.
    bom, mismatched_probed_results = probe.GenerateBOMFromProbedResults(
        self.database, probed_results, device_info, vpd,
        common.OPERATION_MODE.normal, True)

    if mismatched_probed_results:
      for comp_cls, probed_comps in mismatched_probed_results.iteritems():
        self._AddComponents(
            comp_cls, [probed_comp['values'] for probed_comp in probed_comps])

      bom = probe.GenerateBOMFromProbedResults(
          self.database, probed_results, device_info, vpd,
          common.OPERATION_MODE.normal, False)[0]

    # Ensure all essential components are recorded in the database.
    for comp_cls in ESSENTIAL_COMPS:
      if comp_cls == 'region':
        # Skip checking the region because it's acceptable to have a null
        # region component.
        continue
      if not bom.components.get(comp_cls):
        field_name = self.database.GetEncodedFieldForComponent(comp_cls)
        if (field_name and
            any(not comps[comp_cls] for comps
                in self.database.GetEncodedField(field_name).itervalues())):
          # Pass if the database says that device without this component is
          # acceptable.
          continue

        # Ask user to add a default item or a null item.
        add_default = PromptAndAsk(
            'Component [%s] is essential but the probe result is missing. '
            'Do you want to add a default item?\n'
            'If the probed code is not ready yet, please enter "Y".\n'
            'If the device does not have the component, please enter "N".'
            % comp_cls, default_answer=True)

        if add_default:
          self.AddDefaultComponent(comp_cls)

        else:
          # If there's already an encoded field for this component, leave
          # the work to `_UpdateEncodedFields` method and do nothing here.
          if not field_name:
            self.AddNullComponent(comp_cls)

    return probe.GenerateBOMFromProbedResults(
        self.database, probed_results, device_info, vpd,
        common.OPERATION_MODE.normal, False)[0]

  def _UpdateEncodedFields(self, bom):
    covered_comp_classes = set()
    for field_name in self.database.encoded_fields:
      comp_classes = self.database.GetComponentClasses(field_name)

      for comps in self.database.GetEncodedField(field_name).itervalues():
        if all(comp_names == bom.components[comp_cls]
               for comp_cls, comp_names in comps.iteritems()):
          break

      else:
        self.database.AddEncodedFieldComponents(
            field_name,
            {comp_cls: bom.components[comp_cls] for comp_cls in comp_classes})

      covered_comp_classes |= set(comp_classes)

    # Although the database allows a component recorded but not encoded by
    # any of the encoded fields, this builder always ensures that all components
    # will be encoded into the HWID string.
    for comp_cls in self.database.GetComponentClasses():
      if comp_cls not in covered_comp_classes:
        self._AddNewEncodedField(comp_cls, bom.components[comp_cls])

  def _MayAddNewPatternAndImage(self, image_name):
    if image_name in [self.database.GetImageName(image_id)
                      for image_id in self.database.image_ids]:
      if image_name != self.database.GetImageName(
          self.database.max_image_id):
        raise ValueError('image_id [%s] is already in the database.' % image_id)
      # Mark the image name to none if the given image name is the latest image
      # name so that the caller can specify that they don't want to create
      # an extra image by specifying the image_name to either none or the latest
      # image name.
      image_name = None

    # If the use case is to create a new HWID database, the only pattern
    # contained by the empty database is empty.
    if not self.database.GetEncodedFieldsBitLength():
      return

    extra_fields = set(self.database.encoded_fields) - set(
        self.database.GetEncodedFieldsBitLength().keys())
    if image_name:
      self.database.AddImage(self.database.max_image_id + 1, image_name,
                             common.ENCODING_SCHEME.base8192,
                             new_pattern=bool(extra_fields))

    elif extra_fields and PromptAndAsk(
        'WARNING: Extra fields [%s] without assigning a new image_id.\n'
        'If the fields are added into the current pattern, the index of '
        'these fields will be encoded to index 0 for all old HWID string. '
        'Enter "y" if you are sure all old devices with old HWID string '
        'have the component with index 0.' %
        ','.join(extra_fields), default_answer=False) is False:
      raise ValueError(
          'Please assign a image_id by adding "--image-id" argument.')

  def _UpdatePattern(self):
    """Updates the pattern so that it includes all encoded fields."""
    def _GetMinBitLength(field_name):
      return int(math.ceil(math.log(
          max(self.database.GetEncodedField(field_name).keys()) + 1, 2)))

    handled_comp_classes = set()
    handled_encoded_fields = set()

    # Put the important components at first if the pattern is a new one.
    if not self.database.GetEncodedFieldsBitLength():
      # Put the essential field first, and align the 5-3-5 bit field.
      bit_iter = itertools.cycle([5, 3, 5])
      bit_iter.next()  # Skip the first field, which is for image_id.
      for comp_cls in ESSENTIAL_COMPS:
        if comp_cls in handled_comp_classes:
          continue

        field_name = self.database.GetEncodedFieldForComponent(comp_cls)

        bit_length = 0
        min_bit_length = max(_GetMinBitLength(field_name), 1)
        while bit_length < min_bit_length:
          bit_length += bit_iter.next()
        self.database.AppendEncodedFieldBit(field_name, bit_length)

        handled_comp_classes |= set(
            self.database.GetComponentClasses(field_name))
        handled_encoded_fields.add(field_name)

      # Put the priority components.
      for comp_cls, bit_length in PRIORITY_COMPS.iteritems():
        if comp_cls in handled_comp_classes:
          continue

        field_name = self.database.GetEncodedFieldForComponent(comp_cls)
        if not field_name:
          continue

        bit_length = max(bit_length, _GetMinBitLength(field_name))
        self.database.AppendEncodedFieldBit(field_name, bit_length)

        handled_comp_classes |= set(
            self.database.GetComponentClasses(field_name))
        handled_encoded_fields.add(field_name)

    # Append other encoded fields.
    curr_bit_lengths = self.database.GetEncodedFieldsBitLength()
    for field_name in self.database.encoded_fields:
      if field_name in handled_encoded_fields:
        continue
      bit_length = _GetMinBitLength(field_name)
      if (field_name in curr_bit_lengths and
          curr_bit_lengths[field_name] >= bit_length):
        continue
      self.database.AppendEncodedFieldBit(
          field_name, bit_length - curr_bit_lengths.get(field_name, 0))
