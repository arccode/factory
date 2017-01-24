# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ast
from collections import defaultdict
from collections import OrderedDict
import itertools
import logging
import math
import os
import re
import uuid
import yaml

import factory_common  # pylint: disable=unused-import
# Register "!rule" and "!re" tag to yaml constructor.
from cros.factory.hwid.v3 import rule as rule_module
from cros.factory.hwid.v3 import yaml_tags
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils

DB_KEY = type_utils.Enum(['checksum', 'board', 'encoding_patterns', 'image_id',
                          'pattern', 'encoded_fields', 'components', 'rules'])
_NEED_IMAGE_ID_MSG = 'Please assign a image_id by adding "--image-id" argument.'

# The components that are always be created at the front of the pattern,
# even if they don't exist in the probe results.
ESSENTIAL_COMPS = OrderedDict([
    ('board_version', 3),
    ('region', 5),
    ('customization_id', 5),
    ('cpu', 3),
    ('storage', 5),
    ('dram', 5)])

# The components that are added in order if they exist in the probe results.
PRIORITY_COMPS = OrderedDict([
    ('firmware_keys', 3),
    ('ro_main_firmware', 3),
    ('ro_ec_firmware', 2)])


def DefaultBitSize(comp_cls):
  """Returns the default bit size of the components.

  Args:
    comp_cls: the component class name.

  Returns:
    the default bit size of the componenet.
  """
  return ESSENTIAL_COMPS.get(comp_cls, PRIORITY_COMPS.get(comp_cls, 0))


def _FilterSpecialCharacter(string):
  """Filters special cases and converts all seperation characters to underlines.
  """
  string = re.sub(r'[: .-]+', '_', string)
  string = re.sub(r'[^A-Za-z0-9_]+', '', string)
  string = re.sub(r'[_]+', '_', string)
  string = re.sub(r'^_|_$', '', string)
  if not string:
    string = 'unknown'
  return string


def DetermineComponentName(comp_cls, value):
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
  if comp_cls == 'customization_id':
    return value['id']
  if comp_cls == 'firmware_keys':
    dev_key = {
        'key_root': 'b11d74edd286c144e1135b49e7f0bc20cf041f10',
        'key_recovery': 'c14bd720b70d97394257e3e826bd8f43de48d4ed'}
    return 'firmware_keys_dev' if value == dev_key else 'firmware_keys_non_dev'
  if comp_cls in ['ro_main_firmware', 'ro_ec_firmware', 'ro_pd_firmware']:
    return value['version']

  # General components.
  for key in ['model', 'manufacturer', 'part', 'name', 'compact_str']:
    if key in value:
      return _FilterSpecialCharacter(str(value[key]))
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
    a function if found. otherwise return None.
  """
  if not sys_utils.InChroot():
    logging.info('Not in Chroot, skip to find update_checksum.')
    return None

  updater_path = os.path.join(
      os.environ['CROS_WORKON_SRCROOT'],
      'src', 'platform', 'chromeos-hwid', 'bin', 'update_checksum')
  if not os.path.exists(updater_path):
    logging.info('checksum_update is not found.')
    return None
  return lambda db: process_utils.CheckOutput([updater_path, db], log=True)


def ExtractProbedResult(probed_results):
  """Extracts the useful probed result.

  We ignore the data in `initial_configs` and `missing_component_classes`, and
  ignore the value which is not a dict or a list of dicts.
  """
  if probed_results is None:
    return {}
  ret = {}
  for field in ['found_probe_value_map', 'found_volatile_values']:
    if field not in probed_results:
      logging.warning('Probed result does not have %s field.', field)
    else:
      for comp_cls in probed_results[field]:
        value = probed_results[field][comp_cls]
        if isinstance(value, dict):
          ret[comp_cls] = value
        if (isinstance(value, list) and
            all([isinstance(item, dict) for item in value])):
          ret[comp_cls] = value
  return ret


class DatabaseBuilder(object):
  """Builds the database.

  We have these restrictions:
  1. Only the latest (maximum) image_id is availible.
  2. Every active field has only one component.

  db: the OrderedDict to store the database information.
  active_fields: a set to store the fields in the latest pattern. It will change
      during adding or deleting the component. This should be sync before
      changing every component and after calling HandleImageIdAndPattern.
  comp_field_map: the dict that maps the component class to the encoded field
      class.
  """

  IGNORED_COMPONENT_SET = set([
      'hash_gbb',  # Bitmap is not stored in GBB, so we don't track hash_gbb.
      'key_root', 'key_recovery',  # firmware_keys is used to track them.
      'region', 'customization_id'])  # We handle them in other way.
  DEFAULT_REGION = 'us'

  FIELD_SUFFIX = '_field'
  DEFAULT_COMPONENT_SUFFIX = '_default'

  def __init__(self, db=None, board=None):
    self.db = None
    self.active_fields = set()
    self.comp_field_map = {}

    if db is None:
      if board is None:
        raise ValueError('No board name.')
      self.db = self._BuildEmptyDatabase(board)
    else:
      self.db = db
      self.active_fields = self.GetLatestFields()
      self._SplitEncodedField()
      self._ConvertLegacyRegion()
      self._ConvertLegacyCustomizationID()

  @staticmethod
  def _BuildEmptyDatabase(board):
    return OrderedDict([
        (DB_KEY.checksum, None),
        (DB_KEY.board, board),
        (DB_KEY.encoding_patterns, {0: 'default'}),
        (DB_KEY.image_id, OrderedDict()),
        (DB_KEY.pattern, []),
        (DB_KEY.encoded_fields, OrderedDict()),
        (DB_KEY.components, OrderedDict()),
        (DB_KEY.rules, [])])

  def _SplitEncodedField(self):
    """Splits encoded_field if it has multiple components."""
    new_field_comps = set()
    for field_cls in self.GetLatestFields():
      comp_set = set()
      for field_attr in self.db[DB_KEY.encoded_fields][field_cls].itervalues():
        comp_set |= set(field_attr.keys())
      if len(comp_set) == 0:
        raise ValueError('encoded_field %s has no component.' % field_cls)
      if len(comp_set) == 1:
        comp_cls = comp_set.pop()
        if comp_cls in self.comp_field_map:
          raise ValueError(
              'component %s exists in multiple encoded_fields: %s %s' %
              (comp_cls, field_cls, self.comp_field_map[comp_cls]))
        self.comp_field_map[comp_cls] = field_cls
      else:
        self.active_fields.discard(field_cls)
        new_field_comps |= comp_set
    # Create new encoded_field for the components.
    for comp_cls in new_field_comps - self.IGNORED_COMPONENT_SET:
      if comp_cls not in self.comp_field_map:
        for comp_name in self.db[DB_KEY.components][comp_cls]['items'].keys():
          self.AddEncodedField(comp_cls, comp_name)

  def _ConvertLegacyRegion(self):
    # Check if the region is legacy style.
    comp_cls = 'region'
    field_cls = self.GetFieldClass(comp_cls)
    if field_cls not in self.db[DB_KEY.encoded_fields]:
      logging.debug('The database does not have region field. Skip.')
      return False
    if not self.db[DB_KEY.encoded_fields][field_cls].is_legacy_style:
      logging.debug('The database uses new style of region. Skip.')
      return False

    # Find the supported region from rule.
    # TODO(akahuang): We assume there is only one region rule.
    target = "Assert(GetVPDValue('ro', 'region') in %s)"
    target = target.replace(' ', '').replace('(', r'\(').replace(')', r'\)')
    target = target % r'(\[.*\])'
    regions = None
    rule_idx = None
    for idx, rule in enumerate(self.db[DB_KEY.rules]):
      if rule['name'].startswith('verify.'):
        rule_str = re.sub(r'\s', '', rule['evaluate'])
        matched = re.match(target, rule_str)
        try:
          regions = ast.literal_eval(matched.group(1))
          if isinstance(regions, list):
            rule_idx = idx
            break
        except Exception:
          pass
    if rule_idx is None:
      logging.warning('The rule for the region is not found. '
                      'Set "%s" as default region.', self.DEFAULT_REGION)
      regions = [self.DEFAULT_REGION]
    else:
      self.db[DB_KEY.rules].pop(rule_idx)

    # Change the region field name.
    new_field_cls = 'new_' + field_cls
    logging.info('Change region field name from %s to %s.',
                 field_cls, new_field_cls)
    self.active_fields.discard(field_cls)
    self.active_fields.add(new_field_cls)
    self.comp_field_map[comp_cls] = new_field_cls
    self.AddRegions(regions)
    return True

  def _ConvertLegacyCustomizationID(self):
    # Check if the customization_id is legacy style.
    comp_cls = 'customization_id'
    field_cls = self.GetFieldClass(comp_cls)
    if field_cls not in self.db[DB_KEY.encoded_fields]:
      logging.debug('The database does not have customization_id field. Skip.')
      return False
    if self.db[DB_KEY.components][comp_cls].get('probeable', True):
      logging.debug('The database uses new style. Skip.')
      return False

    # Find the supported customization_id from rules.
    target = ("SetComponent('customization_id',"
              "LookupMap(GetVPDValue('ro', 'customization_id'), %s))")
    target = target.replace(' ', '').replace('(', r'\(').replace(')', r'\)')
    target = target % r'({.*})'
    id_map = None
    rule_idx = None
    for idx, rule in enumerate(self.db[DB_KEY.rules]):
      if rule['name'].startswith('device_info.'):
        rule_str = re.sub(r'\s', '', rule['evaluate'])
        matched = re.match(target, rule_str)
        try:
          id_map = ast.literal_eval(matched.group(1))
          if isinstance(id_map, dict):
            rule_idx = idx
            break
        except Exception:
          pass

    if rule_idx is None:
      logging.warning('The rule for the customization_id is not found. Skip.')
      return False
    self.db[DB_KEY.rules].pop(rule_idx)

    # Fill the value in the components field.
    self.db[DB_KEY.components]['customization_id']['probeable'] = True
    reverse_map = {value: key for key, value in id_map.items()}
    db_comp_items = self.db[DB_KEY.components]['customization_id']['items']
    for comp_name in db_comp_items:
      db_comp_items[comp_name]['values'] = {
          'id': reverse_map.get(comp_name, comp_name)}
    return True

  def GetFieldClass(self, comp_cls):
    return self.comp_field_map.setdefault(comp_cls,
                                          comp_cls + self.FIELD_SUFFIX)

  def GetComponentClass(self, field_cls):
    for key, value in self.comp_field_map.iteritems():
      if field_cls == value:
        return key
    raise KeyError('No this field "%s"' % field_cls)

  def GetLatestPattern(self):
    if not self.db[DB_KEY.pattern]:
      return None
    latest_pattern_idx = None
    latest_image_id_idx = -1
    for pattern_idx, pattern in enumerate(self.db[DB_KEY.pattern]):
      if latest_image_id_idx < max(pattern['image_ids']):
        latest_image_id_idx = max(pattern['image_ids'])
        latest_pattern_idx = pattern_idx
    return self.db[DB_KEY.pattern][latest_pattern_idx]

  def GetLatestFields(self):
    latest_pattern = self.GetLatestPattern()
    if latest_pattern is None:
      return set()
    ret = set()
    for field in latest_pattern['fields']:
      ret.add(field.keys()[0])
    return ret

  def GetUnprobeableComponents(self):
    ret = []
    for comp_cls, comp_attr in self.db[DB_KEY.components].iteritems():
      if comp_attr.get('probeable', True) is False:
        ret.append(comp_cls)
    return ret

  def AddDefaultComponent(self, comp_cls):
    logging.info('Component [%s]: add a default item.', comp_cls)
    if comp_cls in self.db[DB_KEY.components]:
      raise ValueError('The component %s already existed. '
                       'It cannot add default item' % comp_cls)
    field_cls = self.GetFieldClass(comp_cls)
    if field_cls in self.db[DB_KEY.encoded_fields]:
      raise ValueError('The encoded_field %s already existed.' % field_cls)
    comp_name = comp_cls + self.DEFAULT_COMPONENT_SUFFIX

    self.db[DB_KEY.components][comp_cls] = OrderedDict({
        'items': OrderedDict({
            comp_name: OrderedDict({
                'default': True,
                'status': 'unqualified',
                'values': None})})})
    self.AddEncodedField(comp_cls, comp_name)
    return comp_name

  def AddNullComponent(self, comp_cls):
    logging.info('Component [%s]: add a null item.', comp_cls)
    self.AddComponent(comp_cls, None)
    self.AddEncodedField(comp_cls, None)

  def AddComponent(self, comp_cls, comp_value, comp_name=None):
    """Tries to add a item in the component, and return the name.

    If the item already exists, then return the name. Otherwise, add the item
    with the assigned name and return it. If the component value is None, then
    we only create the component class.

    Args:
      comp_cls: the component class.
      comp_value: the probed value of the component item,
        or None if adding NULL component.
      comp_name: the name of the component item.

    Returns:
      the component name.
    """
    def _MatchComponentValue(db_comp_value, comp_value):
      if set(db_comp_value.keys()) - set(comp_value):
        return False
      for key, value in db_comp_value.iteritems():
        rule = (value if isinstance(value, rule_module.Value)
                else rule_module.Value(value))
        if not rule.Matches(comp_value[key]):
          return False
      return True

    # Create the component class.
    if comp_cls not in self.db[DB_KEY.components]:
      self.db[DB_KEY.components][comp_cls] = OrderedDict({
          'items': OrderedDict()})
    if comp_value is None:
      return None

    # Find the component already exists or not.
    db_comp_items = self.db[DB_KEY.components][comp_cls]['items']
    for name, value in db_comp_items.iteritems():
      if value.get('default', False):  # Ignore the default item.
        continue
      if _MatchComponentValue(value['values'], comp_value):
        logging.debug('Component %s already exists the item with %s. Skip.',
                      comp_cls, comp_value)
        return name

    # Set old firmware components to deprecated.
    if comp_cls in ['ro_main_firmware', 'ro_ec_firmware', 'ro_pd_firmware']:
      for comp_attr in db_comp_items.itervalues():
        comp_attr['status'] = 'deprecated'

    # Deprecate 'compact_str' if possible.
    if 'compact_str' in comp_value and len(comp_value) > 1:
      comp_value = comp_value.copy()
      comp_value.pop('compact_str')

    if comp_name is None:
      comp_name = DetermineComponentName(comp_cls, comp_value)
    # To prevent name collision, add "_" if the name already exists.
    while comp_name in db_comp_items:
      comp_name += '_'
    logging.info('Component %s: add an item "%s".', comp_cls, comp_name)
    db_comp_items[comp_name] = OrderedDict({
        'status': 'unqualified',
        'values': comp_value})

    # Deprecate the default component.
    for value in db_comp_items.values():
      if value.get('default', False) is True:
        logging.info('Deprecate the default component of %s', comp_cls)
        value['status'] = 'unsupported'

    return comp_name

  def DeleteComponentClass(self, comp_cls):
    """Deletes the component class.

    When the component does not exist in the device, we should remove it from
    the database. But actually we cannot delete it. So we only set the component
    to unprobeable and remove it from the pattern.
    """
    # Set to unprobeable
    if comp_cls not in self.db[DB_KEY.components]:
      logging.warning('Component "%s" is not active. Skip.', comp_cls)
      return
    self.db[DB_KEY.components][comp_cls]['probeable'] = False
    # Remove from the active_fields
    field_cls = self.GetFieldClass(comp_cls)
    logging.info('Remove %s from the active fields.', field_cls)
    self.active_fields.discard(field_cls)

  def AddEncodedField(self, comp_cls, comp_name):
    """Adds an item to the encoded_field.

    Args:
      comp_cls: the component class.
      comp_name: None or string or a list of string. Each name should already
          exist in components.

    Returns:
      the index of the inserted item.
    """
    assert not isinstance(comp_cls, list)

    if isinstance(comp_name, list):
      comp_name.sort()

    field_cls = self.GetFieldClass(comp_cls)
    if field_cls not in self.db[DB_KEY.encoded_fields]:
      self.db[DB_KEY.encoded_fields][field_cls] = OrderedDict()
    # Check the item exists in encoded_field.
    db_field_items = self.db[DB_KEY.encoded_fields][field_cls]
    for field_idx, field_attr in db_field_items.iteritems():
      if field_attr[comp_cls] == comp_name:
        logging.debug('Component %s %s is already encoded. Skip.',
                      comp_cls, comp_name)
        return field_idx
    # Check the item exists in component.
    comp_names = comp_name if isinstance(comp_name, list) else [comp_name]
    for name in comp_names:
      if (name is not None and
          name not in self.db[DB_KEY.components][comp_cls]['items']):
        raise ValueError('Component %s does not exist in %s.' %
                         (name, comp_cls))

    idx = 0 if not db_field_items else max(db_field_items.keys()) + 1
    if len(comp_names) == 1:
      comp_names = comp_names[0]
    db_field_items[idx] = OrderedDict({comp_cls: comp_names})

    # Assumption: If we add the item into the database, then we need this field.
    if field_cls not in self.active_fields:
      logging.info('Enable the encoded_field "%s".', field_cls)
      self.active_fields.add(field_cls)

    return idx

  def AddRegions(self, regions):
    if 'region' not in self.db[DB_KEY.components]:
      self.db[DB_KEY.components]['region'] = yaml_tags.RegionComponent()
    field_cls = self.GetFieldClass('region')
    if field_cls not in self.db[DB_KEY.encoded_fields]:
      nodes = [yaml_tags.YamlNode(value) for value in regions]
      self.db[DB_KEY.encoded_fields][field_cls] = yaml_tags.RegionField(nodes)
    else:
      for region in regions:
        self.db[DB_KEY.encoded_fields][field_cls].AddRegion(region)
    logging.info('Enable the encoded_field "%s".', field_cls)
    self.active_fields.add(field_cls)

  def AddCustomizationID(self, customization_ids):
    comp_cls = 'customization_id'
    for customization_id in customization_ids:
      name = self.AddComponent(comp_cls, {'id': customization_id},
                               customization_id)
      self.AddEncodedField(comp_cls, name)
    if self.db[DB_KEY.components][comp_cls].get('probeable', True) is False:
      self.db[DB_KEY.components][comp_cls]['probeable'] = True

  def _IsNewPatternNeeded(self, has_new_image_id):
    """Determines whether the new pattern is needed.

    Args:
      has_new_image_id: a boolean indicating that a new image_id is assigned.

    Returns:
      True if the new pattern is needed.

    Raises:
      ValueError if image_id is None and a new image_id is needed.
    """
    latest_fields = self.GetLatestFields()
    if has_new_image_id:
      if not self.db[DB_KEY.pattern]:
        return True
      return self.active_fields != latest_fields
    else:
      if not self.db[DB_KEY.pattern]:
        raise ValueError('No pattern exists. %s' % _NEED_IMAGE_ID_MSG)
      # If any fields is deleted, then we must need a new pattern.
      deleted_fields = latest_fields - self.active_fields
      if deleted_fields:
        raise ValueError('The fields "%s" are deleted. %s' %
                         (', '.join(deleted_fields), _NEED_IMAGE_ID_MSG))
      extra_fields = self.active_fields - latest_fields
      if extra_fields:
        if PromptAndAsk(
            'WARNING: Extra fields [%s] without assigning a new image_id.\n'
            'If the fields are added into the current pattern, the index of '
            'these fields will be encoded to index 0 for all old HWID string. '
            'Enter "y" if you are sure all old devices with old HWID string '
            'have the component with index 0.' %
            ','.join(extra_fields), default_answer=False) is False:
          raise ValueError(_NEED_IMAGE_ID_MSG)
      return False

  def _UpdatePattern(self, image_id_idx=None):
    """Updates the latest pattern.

    We count the components for each active field, and add the encoded bits if
    not enough. If the new image_id is assigned, add the index into the pattern.
    Adding new fields are allowed while updating the pattern if the user
    confirms all the old devices have the component with index 0.

    Args:
      image_id_idx: the index of the new image_id.
    """
    logging.info('Update the latest pattern.')
    # Calculate the bit size is enough or not.
    latest_pattern = self.GetLatestPattern()
    bit_count_map = defaultdict(int)
    for field in latest_pattern['fields']:
      field_cls, bits = field.items()[0]
      bit_count_map[field_cls] += bits
    # Only check that no field is deleted.
    assert not set(bit_count_map.keys()) - self.active_fields

    latest_fields = self.GetLatestFields()
    for field_cls in self.active_fields:
      field_count = max(self.db[DB_KEY.encoded_fields][field_cls].keys()) + 1
      bit_count = int(math.ceil(math.log(field_count, 2)))
      bit_increase = bit_count - bit_count_map[field_cls]
      if field_cls not in latest_fields or bit_increase > 0:
        logging.info('Add field "%s": %s bits', field_cls, bit_increase)
        latest_pattern['fields'].append({field_cls: bit_increase})

    # Add the image_id index if exists
    if image_id_idx is not None:
      latest_pattern['image_ids'].append(image_id_idx)

  def _AddPattern(self, image_id_idx):
    logging.info('Create a new pattern.')
    new_pattern = OrderedDict([
        ('image_ids', [image_id_idx]),
        ('encoding_scheme', 'base8192'),
        ('fields', [])])
    bit_table = {}
    for field_cls in self.active_fields:
      field_count = max(self.db[DB_KEY.encoded_fields][field_cls].keys()) + 1
      bit_count = max(DefaultBitSize(self.GetComponentClass(field_cls)),
                      int(math.ceil(math.log(field_count, 2))))
      bit_table[field_cls] = bit_count

    # Put the essential field first, and align the 5-3-5 bit field.
    fields_data = []
    bit_iter = itertools.cycle([5, 3, 5])
    bit_iter.next()  # Skip the first field, which is for image_id.
    for comp_cls in ESSENTIAL_COMPS:
      field_cls = self.GetFieldClass(comp_cls)
      count = 0
      if field_cls not in bit_table:
        raise ValueError('Essential field [%s] are missing.' % field_cls)
      while count < bit_table[field_cls]:
        count += bit_iter.next()
      fields_data.append({field_cls: count})
      del bit_table[field_cls]
    # Put the priority components.
    for comp_cls in PRIORITY_COMPS:
      field_cls = self.GetFieldClass(comp_cls)
      if field_cls in bit_table:
        fields_data.append({field_cls: bit_table[field_cls]})
        del bit_table[field_cls]
    # Put remaining components.
    for field_cls, bit_count in sorted(bit_table.items(),
                                       key=lambda x: x[1], reverse=True):
      fields_data.append({field_cls: bit_count})

    assert len(fields_data) == len(self.active_fields)
    new_pattern['fields'] = fields_data
    self.db[DB_KEY.pattern].append(new_pattern)

  def _AddImageID(self, image_id):
    if image_id is None:
      return None
    if image_id in self.db[DB_KEY.image_id].values():
      raise ValueError('image_id [%s] is already in the database.' % image_id)
    # TODO(akahuang): Determine the build order. Disallow EVT after DVT

    # Add the new item in image_id field.
    if not self.db[DB_KEY.image_id]:
      idx = 0
    else:
      idx = max(self.db[DB_KEY.image_id].keys()) + 1
    self.db[DB_KEY.image_id][idx] = image_id

    # Update the rule of SetImageId
    image_id_rule = OrderedDict([
        ('name', 'device_info.image_id'),
        ('evaluate', "SetImageId('%s')" % image_id)])
    if self.db[DB_KEY.rules]:
      self.db[DB_KEY.rules] = [rule for rule in self.db[DB_KEY.rules]
                               if 'SetImageId' not in rule['evaluate']]
    self.db[DB_KEY.rules].append(image_id_rule)
    return idx

  def MayOmitProbeResult(self, comp_cls):
    """Checks if the component class can be missing or not.

    If the component class has the default item or the null item, or the
    probeable is False, then the result can be missing.

    Args:
      comp_cls: the component class. It should already exist at the database.

    Returns:
      True if the component is unprobeable, or it has a default item or a null
      item.
    """
    if self.db[DB_KEY.components][comp_cls].get('probeable', True) is False:
      return True
    field_cls = self.GetFieldClass(comp_cls)
    # Has the null item.
    for field_item in self.db[DB_KEY.encoded_fields][field_cls].values():
      if field_item[comp_cls] is None:
        return True
    # Has the default item.
    for comp_item in self.db[DB_KEY.components][comp_cls]['items'].values():
      if (comp_item.get('default', False) is True and
          comp_item.get('status', 'supported') != 'unsupported'):
        return True
    return False

  def _UpdateProbedResult(self, probed_results, ignore_comps):
    ignore_comps |= self.IGNORED_COMPONENT_SET

    # Check no probed result for all unprobeable components.
    error_comps = (set(probed_results.keys()) &
                   set(self.GetUnprobeableComponents()))
    if error_comps:
      raise ValueError('The probed result should not have the components: %r' %
                       list(error_comps))

    # Check the missing essential components.
    common_list = set(ESSENTIAL_COMPS.keys()) - ignore_comps
    for comp_cls in common_list:
      if comp_cls not in probed_results:
        if (comp_cls not in self.db[DB_KEY.components] or
            not self.MayOmitProbeResult(comp_cls)):
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
            self.AddNullComponent(comp_cls)

    # Check the missing components at the active component list.
    # The active fields might be changed during the loop, so iterate the copy.
    active_fields = self.active_fields.copy()
    for field_cls in active_fields:
      comp_cls = self.GetComponentClass(field_cls)
      if (comp_cls not in probed_results and
          not self.MayOmitProbeResult(comp_cls)):
        add_null = PromptAndAsk(
            'Component %s: The probed result is missing. '
            'Do you want to add a NULL item or delete the component class ?\n'
            'If the device has a SKU without the component, please enter "Y".\n'
            'If the device does not have the component, please enter "N".\n'
            % comp_cls, default_answer=True)
        if add_null:
          self.AddNullComponent(comp_cls)
        else:
          self.DeleteComponentClass(comp_cls)
    # Add components value into the database
    for comp_cls, comp_value in probed_results.iteritems():
      if comp_cls in ignore_comps:
        continue
      is_list = isinstance(comp_value, list)
      if not is_list:
        comp_name = self.AddComponent(comp_cls, comp_value)
        self.AddEncodedField(comp_cls, comp_name)
      else:
        comp_values = comp_value
        comp_names = []
        for comp_value in comp_values:
          comp_name = DetermineComponentName(comp_cls, comp_value)
          comp_names.append(self.AddComponent(comp_cls, comp_value))
        self.AddEncodedField(comp_cls, comp_names)

  def Update(self, probed_results, image_id, add_default_comp, add_null_comp,
             del_comp, region, customization_id):
    """Updates the database by the probed result and arguments.

    Args:
      probed_results: None or a dict containing the probed results generated by
          "gooftool.py probe --include-vpd".
      image_id: None or a string containing the new image_id.
      add_comp: a list of component classes which add a default item.
      del_comp: a list of component classes which are removed in latest pattern.
      region: a list of region code that are appended in the database.
      customization_id: a list of customization ID that are appended in the
          database.
    """
    probed_results = ExtractProbedResult(probed_results)
    add_default_comp = (set() if add_default_comp is None
                        else set(add_default_comp))
    add_null_comp = set() if add_null_comp is None else set(add_null_comp)
    del_comp = set() if del_comp is None else set(del_comp)

    # Add default and null items for assigned components.
    for comp_cls in add_default_comp:
      self.AddDefaultComponent(comp_cls)
    for comp_cls in add_null_comp:
      self.AddNullComponent(comp_cls)
    for comp_cls in del_comp:
      if comp_cls in ESSENTIAL_COMPS:
        raise ValueError('Component [%s] is essential, cannot be deleted. '
                         'Please remove the "--del-component %s" argument.' %
                         (comp_cls, comp_cls))
      self.DeleteComponentClass(comp_cls)

    # Update the value in the probed result.
    if probed_results:
      self._UpdateProbedResult(probed_results, add_default_comp | del_comp)

    # Handle region. Default: us
    region_set = set(region) if region else set()
    if 'region' in probed_results:
      region_set.add(probed_results['region']['region_code'])
    if not region_set and 'region' not in self.db[DB_KEY.components]:
      logging.info('No region is assigned. Set default region "%s".',
                   self.DEFAULT_REGION)
      region_set.add(self.DEFAULT_REGION)
    if region_set:
      self.AddRegions(region_set)
    # Handle customization_id. Default: NULL
    customization_id_set = set(customization_id) if customization_id else set()
    if 'customization_id' in probed_results:
      customization_id_set.add(probed_results['customization_id']['id'])
    if customization_id_set:
      self.AddCustomizationID(customization_id_set)
    elif 'customization_id' not in self.db[DB_KEY.components]:
      logging.info('No customization_id is assigned. Add NULL component.')
      self.AddNullComponent('customization_id')

    # Update the image_id and pattern.
    self.HandleImageIdAndPattern(image_id)

  def HandleImageIdAndPattern(self, image_id=None):
    """Updates the image_id and pattern.

    If the active encoded_fields is changed, i.e. there is a new component or
    removed component, then we need a new pattern and a new image_id. Because
    the image_id and pattern are high coupling, we update them in this method.

    Args:
      image_id: None or a string containing the new image_id.

    Raises:
      ValueError if:
        1. image_id is already existed in current database.
        2. image_id is None and a new image_id is needed.
    """
    image_id_idx = self._AddImageID(image_id)
    if self._IsNewPatternNeeded(image_id_idx is not None):
      self._AddPattern(image_id_idx)
    else:
      self._UpdatePattern(image_id_idx)
    self.Verify()

  def Verify(self):
    """Verifies that the database meets the restriction or not.

    Raises:
      ValueError if any error occurs.
    """
    error_msg = []
    # Check image_id is unique.
    appeared_image_id = set()
    for image_id in self.db[DB_KEY.image_id].values():
      if image_id in appeared_image_id:
        error_msg.append('image_id "%s" is repeated.' % image_id)
      appeared_image_id.add(image_id)

    # Check the index of each image_id is 0~15.
    image_id_set = set(self.db[DB_KEY.image_id].keys())
    invalid_idx = image_id_set - set(range(16))
    if invalid_idx:
      error_msg.append('The image_id index [%s] are invalid. '
                       'Should be less than 16.' %
                       ','.join(map(str, invalid_idx)))

    # Check every image_id has a pattern.
    appear_idx = set()
    for pattern in self.db[DB_KEY.pattern]:
      for idx in pattern['image_ids']:
        if idx not in image_id_set:
          error_msg.append('Unknown image_id "%s" appears in pattern.' % idx)
        if idx in appear_idx:
          error_msg.append('image_id "%s" appears in pattern repeatedly.' % idx)
        appear_idx.add(idx)
    missing_ids = image_id_set - appear_idx
    if missing_ids:
      error_msg.append('image_id index [%s] are missing in the pattern.' %
                       ','.join(map(str, missing_ids)))

    # Check the latest pattern is sync with active_field
    current_fields = self.GetLatestFields()
    missing_fields = self.active_fields - current_fields
    extra_fields = current_fields - self.active_fields
    if missing_fields:
      error_msg.append('[%s] are missing in current pattern.' %
                       ','.join(missing_fields))
    if extra_fields:
      error_msg.append('[%s] are extra fields in current pattern.' %
                       ','.join(extra_fields))

    # Check the bit size of every active encoded field is enough.
    latest_pattern = self.GetLatestPattern()
    bit_count_map = defaultdict(int)
    for field in latest_pattern['fields']:
      field_cls, bits = field.items()[0]
      bit_count_map[field_cls] += bits
    for field_cls in self.active_fields:
      index = self.db[DB_KEY.encoded_fields][field_cls].keys()
      if max(index) >= (1 << bit_count_map[field_cls]):
        error_msg.append('The bit size of "%s" is not enough.' % field_cls)

      # Check the index of every active encoded field is 0 to (count-1).
      # It is not error so we just print the warning message.
      field_count = len(self.db[DB_KEY.encoded_fields][field_cls])
      if set(index) != set(range(field_count)):
        logging.warning('The index of encoded_field "%s" is not compacted: %s',
                        field_cls, index)

    if error_msg:
      raise ValueError('\n'.join(error_msg))

  def Render(self, database_path):
    """Renders the database to a yaml file.

    Args:
      database_path: the path of the output yaml file.
    """
    # Output the yaml file.
    content = '\n'.join(
        [yaml.dump(OrderedDict({key: self.db[key]}), default_flow_style=False)
         for key in self.db])
    # Post processing of yaml_tags.
    content = yaml_tags.RemoveDummyString(content)
    with open(database_path, 'w') as f:
      f.write(content)
    # Update the checksum.
    checksum_updater = ChecksumUpdater()
    if checksum_updater is None:
      logging.info('Checksum is not updated.')
    else:
      logging.info('Update the checksum.')
      checksum_updater(database_path)
