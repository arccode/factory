#!/usr/bin/env python
# pylint: disable=E0602,E1101,W0201
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Visualize and/or modify HWID and related component data."""


import logging
import os
import random
import re
import string  # pylint: disable=W0402
import sys
import zlib

import factory_common  # pylint: disable=W0611

from cros.factory.common import Error, Obj, SetupLogging
from cros.factory.hacked_argparse import CmdArg, Command, ParseCmdline
from cros.factory.hacked_argparse import verbosity_cmd_arg
from cros.factory.hwdb.bom_names import BOM_NAME_SET
from cros.factory.hwdb.yaml_datastore import InvalidDataError
from cros.factory.hwdb.yaml_datastore import MakeDatastoreClass, YamlDatastore


# The expected location of HWID data within a factory image.
DEFAULT_HWID_DATA_PATH = '/usr/local/factory/hwid'


# File that contains component data shared by all boards.
COMPONENT_DB_FILENAME = 'component_db'


# Glob-matching for 'BOM VARIANT-VOLATILE' regexp.
HWID_GLOB_RE = re.compile(r'^([A-Z]+) ([A-Z]+|\*)-([A-Z]+|\*)$')


# Possible life cycle stages (status) for components and HWIDs.
LIFE_CYCLE_STAGES = set([
    'supported',
    'qualified',
    'deprecated',
    'eol'])


MakeDatastoreClass('StatusData', dict(
    (status_name, (list, str))
    for status_name in LIFE_CYCLE_STAGES))

MakeDatastoreClass('ComponentRegistry', {
    'probable_components': (dict, (dict, str)),
    'opaque_components': (dict, (list, str)),
    'status': StatusData,
    })

MakeDatastoreClass('ComponentSpec', {
    'classes_dontcare': (list, str),
    'classes_missing': (list, str),
    'components': (dict, [str, (list, str)]),
    })

MakeDatastoreClass('BomSpec', {
    'primary': ComponentSpec,
    'variants': (list, str),
    })

MakeDatastoreClass('InitialConfigSpec', {
    'constraints': (dict, str),
    'enforced_for_boms': (list, str),
    })

MakeDatastoreClass('DeviceSpec', {
    'boms': (dict, BomSpec),
    'hwid_status': StatusData,
    'initial_configs': (dict, InitialConfigSpec),
    'variants': (dict, ComponentSpec),
    'volatiles': (dict, (dict, str)),
    'volatile_values': (dict, str),
    'vpd_ro_fields': (list, str),
    })

MakeDatastoreClass('ComponentData', {
    'classes_missing': (list, str),
    'extant_components': (list, str),
    })

MakeDatastoreClass('ProbeResults', {
    'found_components': (dict, [str, (list, str)]),
    'missing_component_classes': (list, str),
    'volatiles': (dict, str),
    'initial_configs': (dict, str),
    })

MakeDatastoreClass('HwidData', {
    'hwid': str,
    'board_name': str,
    'bom_name': str,
    'variant_code': str,
    'volatile_code': str,
    'status': str,
    'components': ComponentSpec,
    'initial_config': (dict, str),
    'ro_vpds': (list, str),
    })


def HwidChecksum(text):
  return ('%04u' % (zlib.crc32(text) & 0xffffffffL))[-4:]


def ParseHwid(hwid):
  """Parse HWID string details.  See the hwid spec for details."""
  parts = hwid.split()
  if len(parts) != 4:
    raise Error, ('illegal hwid %r, does not match ' % hwid +
                  '"BOARD BOM VARIANT-VOLATILE CHECKSUM" format')
  checksum = parts.pop()
  if checksum != HwidChecksum(' '.join(parts)):
    raise Error, 'bad checksum for hwid %r' % hwid
  varvol = parts.pop().split('-')
  if len(varvol) != 2:
    raise Error, 'bad variant-volatile part for hwid %r' % hwid
  variant, volatile = varvol
  board, bom = parts
  if not all(x.isalpha() for x in [board, bom, variant, volatile]):
    raise Error, 'bad (non-alpha) part for hwid %r' % hwid
  return Obj(hwid=hwid, board=board, bom=bom,
             variant=variant, volatile=volatile)


def AlphaIndex(num):
  """Generate an alphabetic value corresponding to the input number.

  Translate 0->A, 1->B, .. 25->Z, 26->AA, 27->AB, and so on.
  """
  result = ''
  alpha_count = len(string.uppercase)
  while True:
    result = string.uppercase[num % alpha_count] + result
    num /= alpha_count
    if num == 0:
      break
    num -= 1
  return result


def ComponentConfigStr(component_map):
  """Represent component_map with a single canonical string.

  Component names are unique.  ANY and NONE are combined with the
  corresponding component class name to become unique.  The resulting
  substrings are sorted and concatenated.
  """
  def substr(comp_class, comp):
    return comp_class + '_' + comp if comp in ['ANY', 'NONE'] else comp
  return ' '.join(sorted(substr(k, v) for k, v in component_map.items()))


def FmtRightAlignedDict(d):
  max_key_width = max(len(k) for k in d) if d else 0
  return ['%s%s: %s' % ((max_key_width - len(k)) * ' ', k, v)
          for k, v in sorted((k, v) for k, v in d.items())]


def FmtLeftAlignedDict(d):
  max_key_width = max(len(k) for k in d) if d else 0
  return ['%s%s: %s' % (k, (max_key_width - len(k)) * ' ', v)
          for k, v in sorted((k, v) for k, v in d.items())]


def ComponentSpecClasses(component_spec):
  return (set(component_spec.classes_dontcare) |
          set(component_spec.classes_missing) |
          set(component_spec.components))


def CombineComponentSpecs(a, b):
  components = {}
  components.update(a.components)
  components.update(b.components)
  return ComponentSpec(
    classes_dontcare=list(set(a.classes_dontcare) | set(b.classes_dontcare)),
    classes_missing=list(set(a.classes_missing) | set(b.classes_missing)),
    components=components)


def ComponentSpecsConflict(a, b):
  return (ComponentSpecClasses(a) & ComponentSpecClasses(b)) != set()


class Validate:  # pylint: disable=W0232

  @classmethod
  def HwidPart(cls, tag, name, maxlen):
    if not (name.isalpha() and name.isupper() and len(name) <= maxlen):
      raise Error, ('%s names must be upper-case, alpha-only, and '
                    '%d characters or less, not %r' % (tag, maxlen, name))

  @classmethod
  def BoardName(cls, name):
    cls.HwidPart('board', name, 9)

  @classmethod
  def BomName(cls, name):
    cls.HwidPart('bom', name, 8)

  @classmethod
  def Status(cls, status):
    if not status in LIFE_CYCLE_STAGES:
      raise Error, ('status must be one of {%s}, not %r' %
                    (', '.join(LIFE_CYCLE_STAGES), status))

  @classmethod
  def ComponentName(cls, name):
    regexp = r'^([a-zA-Z0-9_]+)$'
    if not re.match(regexp, name):
      raise Error, ('component names must match the regexp %r, not %r' %
                    (regexp, name))

  @classmethod
  def VolatileName(cls, name):
    regexp = r'^([a-zA-Z0-9_\./]+)$'
    if not re.match(regexp, name):
      raise Error, ('volatile result names must match the regexp %r, not %r' %
                    (regexp, name))

  @classmethod
  def InitialConfigContraintName(cls, name):
    regexp = r'^([a-zA-Z0-9_]+)$'
    if not re.match(regexp, name):
      raise Error, ('initial config constraint names must match the '
                    'regexp %r, not %r' % (regexp, name))

  @classmethod
  def InitialConfigTag(cls, tag):
    if not tag.isdigit():
      raise Error, 'initial config tags must be digits, not %r' % tag


class CompDb(YamlDatastore):

  def _BuildNameResultMap(self):
    self.name_result_map = dict(
      (comp_name, probe_result)
      for comp_class, comp_map in self.probable_components.items()
      for comp_name, probe_result in comp_map.items())

  def _BuildResultNameMap(self):
    self.result_name_map = dict(
      (probe_result, comp_name)
      for comp_class, comp_map in self.probable_components.items()
      for comp_name, probe_result in comp_map.items())

  def _BuildNameClassMaps(self):
    self.name_class_map = {}
    self.name_class_map.update(dict(
      (comp_name, comp_class)
      for comp_class, comps in self.opaque_components.items()
      for comp_name in comps))
    self.name_class_map.update(dict(
      (comp_name, comp_class)
      for comp_class, comp_map in self.probable_components.items()
      for comp_name in comp_map))
    self.class_name_map = {}
    for name, comp_class in self.name_class_map.items():
      self.class_name_map.setdefault(comp_class, set()).add(name)

  def _PreprocessData(self):
    self._BuildResultNameMap()
    self._BuildNameResultMap()
    self._BuildNameClassMaps()
    self.all_comp_classes = (set(self.opaque_components) |
                             set(self.probable_components))
    self.all_comp_names = set(self.name_class_map)

  def _EnforceProbeResultUniqueness(self):
    if len(self.result_name_map) < len(self.name_result_map):
      extra = set(self.name_result_map) - set(self.result_name_map.values())
      raise Error, ('probe results are not all unique; '
                    'components [%s] are redundant' % ', '.join(extra))

  def _EnforceCompNameUniqueness(self):
    names = set()
    overlap = set()
    for comp_map in self.probable_components.values():
      for name in comp_map.values():
        (names if name not in names else overlap).add(name)
    for comps in self.opaque_components.values():
      for name in comps:
        (names if name not in names else overlap).add(name)
    if overlap:
      raise Error, ('component names [%s] are not unique' % ', '.join(overlap))

  def EnforceInvariants(self):
    self._EnforceProbeResultUniqueness()

  def CompExists(self, comp):
    if comp not in self.all_comp_names:
      raise Error, 'unknown component named %r' % comp

  def CompClassExists(self, comp_class):
    if comp_class not in self.all_comp_classes:
      raise Error, 'unknown component class %r' % comp_class

  def AddComponent(self, comp_class, probe_result=None, comp_name=None):
    if comp_name is None:
      comp_count = len(self.class_name_map.get(comp_class, set()))
      comp_name = '%s_%d' % (comp_class, comp_count)
    Validate.ComponentName(comp_name)
    assert comp_name not in self.name_class_map
    if probe_result is not None:
      comp_map = self.probable_components.setdefault(comp_class, {})
      comp_map[comp_name] = probe_result
    else:
      self.opaque_components.setdefault(comp_class, []).append(comp_name)
    self._PreprocessData()
    return comp_name

  def __init__(self, data):  # pylint: disable=W0231
    self.__dict__.update(data.__dict__)
    self._PreprocessData()
    self.EnforceInvariants()

  def CreateComponentSpec(self, components, dontcare, missing):
    """Verify comp_class completeness across the specified inputs."""
    comp_map = dict((self.name_class_map[comp], comp) for comp in components)
    class_conflict = set(dontcare) & set(missing) & set(comp_map)
    if class_conflict:
      raise Error, ('illegal component specification, conflicting data for '
                    'component classes: %s' % ', '.join(class_conflict))
    return ComponentSpec(
      classes_dontcare=sorted(dontcare),
      classes_missing=sorted(missing),
      components=comp_map)

  def MatchComponentSpec(self, spec, found_components):
    for comp in found_components:
      comp_class = self.name_class_map[comp]
      if comp_class in spec.classes_dontcare:
        continue
      if (comp_class in spec.classes_missing or
          comp not in spec.components):
        return False
    return True

  def ComponentDataClasses(self, component_data):
    return (set(component_data.classes_missing) |
            set(self.name_class_map[comp]
                for comp in component_data.extant_components))

  @classmethod
  def Read(cls, path):
    full_path = os.path.join(path, COMPONENT_DB_FILENAME)
    if not os.path.isfile(full_path):
      raise InvalidDataError, (
        'ComponentDB not found (expected path is %r).' % full_path)
    with open(full_path, 'r') as f:
      return cls(ComponentRegistry.Decode(f.read()))

  def Write(self, path):
    """Write the component_db and all device data files."""
    data = ComponentRegistry(**dict(
        (field_name, getattr(self, field_name))
        for field_name in ComponentRegistry.FieldNames()))
    # Create copy (with known up to date internal data) to re-check invariants.
    CompDb(data)
    self.WriteOnDiff(path, COMPONENT_DB_FILENAME, data.Encode())


class CookedBoms(object):

  def _BuildCompBomsMap(self):
    """Build dict of (component: bom name set) mappings.

    Match each component with the set of boms containing it.
    """
    self.comp_boms_map = {}
    for bom_name, bom in self.bom_map.items():
      for comp_data in bom.primary.components.values():
        comps = comp_data if isinstance(comp_data, list) else [comp_data]
        for comp in comps:
          self.comp_boms_map.setdefault(comp, set()).add(bom_name)

  def _BuildCommonCompMap(self):
    """Return (comp_class: [comp]) dict for components common to all boms."""
    self.comp_map = {}
    for bom in self.bom_map.values():
      for comp_class, comp_data in bom.primary.components.items():
        comps = comp_data if isinstance(comp_data, list) else [comp_data]
        for comp in comps:
          if self.comp_boms_map[comp] == self.names:
            self.comp_map.setdefault(comp_class, set()).add(comp)

  def _BuildCommonComps(self):
    self.common_comps = set()
    for comps in self.comp_map.values():
      self.common_comps |= set(comps)

  def _BuildHierarchy(self):
    self.hierarchy = []
    def AddBom(bom_names):
      self.hierarchy.append(CookedBoms(dict(
            (bom_name, self.bom_map[bom_name])
            for bom_name in bom_names)))
    uncommon_comp_boms_map = dict(
      (comp, bom_names) for comp, bom_names in self.comp_boms_map.items()
      if comp not in self.common_comps)
    uncommon_bom_names = set().union(*uncommon_comp_boms_map.values())
    if len(self.names) > 1:
      for bom_name in self.names - uncommon_bom_names:
        AddBom([bom_name])
    while uncommon_bom_names:
      related_bom_sets = [
        bom_subset & uncommon_bom_names
        for bom_subset in uncommon_comp_boms_map.values()]
      most_related = sorted([(len(rbs), rbs) for rbs in related_bom_sets],
                            reverse=True)[0][1]
      AddBom(most_related)
      uncommon_bom_names -= most_related

  def __init__(self, bom_map):
    self.bom_map = bom_map
    self.names = set(bom_map)
    self._BuildCompBomsMap()
    self._BuildCommonCompMap()
    self._BuildCommonComps()
    self._BuildHierarchy()


class CookedProbeResults(object):

  def _MatchComponents(self):
    self.matched_components = []
    self.unmatched_components = {}
    for probe_class, pr_data in self.found_components.items():
      probe_results = pr_data if isinstance(pr_data, list) else [pr_data]
      for probe_result in probe_results:
        component_name = self._comp_db.result_name_map.get(probe_result, None)
        if component_name is not None:
          self.matched_components.append(component_name)
        else:
          pr_list = self.unmatched_components.setdefault(probe_class, [])
          pr_list.append(probe_result)
    self.matched_components.sort()

  def _MatchVolatiles(self):
    self.matched_volatiles = {}
    self.unmatched_volatiles = {}
    for probe_class, probe_result in self.volatiles.items():
      volatile_name = self._device.reverse_vol_value_map.get(probe_result, None)
      if volatile_name is not None:
        self.matched_volatiles[probe_class] = volatile_name
      else:
        self.unmatched_volatiles[probe_class] = probe_result

  def _MatchVolTags(self):
    self.matched_vol_tags = sorted(
      tag for tag, volatile in self._device.volatiles.items()
      if volatile == self.matched_volatiles)

  def _MatchIcTags(self):
    self.matched_ic_tags = sorted(
      tag for tag, ic in self._device.initial_configs.items()
      if ic.constraints == self.initial_configs)

  def _BuildMatchTree(self):
    self.component_data = ComponentData(
      classes_missing=self.missing_component_classes,
      extant_components=self.matched_components)
    self.component_data_classes = self._comp_db.ComponentDataClasses(
      self.component_data)
    self.component_data_is_complete = (
      self.component_data_classes == self._comp_db.all_comp_classes)
    self.match_tree = dict((bom_name, {}) for bom_name in
                           self._device.MatchBoms(self.component_data))
    self.matched_hwids = set()
    for bom_name, variant_tree in self.match_tree.items():
      matching_variants = self._device.MatchVariants(
        bom_name, self.component_data)
      for var_code in matching_variants:
        volatile_tree = variant_tree.setdefault(var_code, {})
        for vol_tag in self.matched_vol_tags:
          status = self._device.GetHwidStatus(bom_name, var_code, vol_tag)
          if status is not None:
            volatile_tree[vol_tag] = status
            hwid = self._device.FmtHwid(bom_name, var_code, vol_tag)
            self.matched_hwids.add(hwid)

  def _MatchInitialConfigs(self):
    self.matched_ic_boms = set()
    for bom_name in self.match_tree:
      enforced_ics = self._device.reverse_ic_map.get(bom_name, [])
      if set(enforced_ics) >= set(self.matched_ic_tags):
        self.matched_ic_boms.add(bom_name)

  def __init__(self, comp_db, device, probe_results):
    self._comp_db = comp_db
    self._device = device
    self.__dict__.update(probe_results.__dict__)
    self._MatchComponents()
    self._MatchVolatiles()
    self._MatchVolTags()
    self._MatchIcTags()
    self._BuildMatchTree()
    self._MatchInitialConfigs()


class Device(YamlDatastore):

  def _BuildReverseIcMap(self):
    self.reverse_ic_map = {}
    for index, data in self.initial_configs.items():
      for bom_name in data.enforced_for_boms:
        self.reverse_ic_map.setdefault(bom_name, set()).add(index)

  def _BuildReverseVolValueMap(self):
    self.reverse_vol_value_map = dict(
      (v, k) for k, v in self.volatile_values.items())

  def UpdateHwidStatusPatterns(self):
    status_tree = dict((status, {}) for status in LIFE_CYCLE_STAGES)
    for bom_name, var_status in self._hwid_status_map.items():
      for var_code, vol_status in var_status.items():
        for vol_code, status in vol_status.items():
          bom_subtree = status_tree[status].setdefault(bom_name, {})
          bom_subtree.setdefault(vol_code, set()).add(var_code)
    for status in LIFE_CYCLE_STAGES:
      patterns = set()
      for bom_name, bom_subtree in status_tree[status].items():
        star_var_vols = set(
          vol_code for vol_code, var_set in bom_subtree.items()
          if var_set == set(self.boms[bom_name].variants))
        if star_var_vols == set(self.volatiles):
          patterns.add('%s *-*' % bom_name)
          continue
        for vol_code, var_codes in bom_subtree.items():
          if vol_code in star_var_vols:
            patterns.add('%s *-%s' % (bom_name, vol_code))
            continue
          for var_code in var_codes:
            patterns.add('%s %s-%s' % (bom_name, var_code, vol_code))
      setattr(self.hwid_status, status, sorted(patterns))

  def UpdateHwidStatusMaps(self, bom, variant, volatile, status):
    target_boms = set([bom]) if bom != '*' else set(self.boms)
    target_vols = set([volatile]) if volatile != '*' else set(self.volatiles)
    for bom_name in target_boms:
      var_status = self._hwid_status_map.setdefault(bom_name, {})
      all_vars = set(self.boms[bom_name].variants)
      target_vars = [variant] if variant != '*' else all_vars
      for var_code in target_vars:
        vol_status = var_status.setdefault(var_code, {})
        for vol_code in target_vols:
          prev_status = vol_status.get(vol_code, None)
          if prev_status is not None:
            logging.info('hwid %s %s-%s status change %r -> %r',
                         bom_name, var_code, vol_code, prev_status, status)
          vol_status[vol_code] = status
          hwid = self.FmtHwid(bom_name, var_code, vol_code)
          self.flat_hwid_status_map[hwid] = status

  def _BuildHwidStatusMaps(self):
    self._hwid_status_map = {}
    self.flat_hwid_status_map = {}
    status_globs = [(pattern, status)
                    for status in LIFE_CYCLE_STAGES
                    for pattern in getattr(self.hwid_status, status)]
    for pattern, status in status_globs:
      match = HWID_GLOB_RE.findall(pattern)
      if not match:
        raise Error, 'illegal hwid_status pattern %r' % pattern
      bom, variant, volatile = match.pop()
      self.UpdateHwidStatusMaps(bom, variant, volatile, status)

  def _BuildClassSets(self):
    self.primary_classes = set().union(*[
        ComponentSpecClasses(bom.primary) for bom in self.boms.values()])
    self.variant_classes = (self._comp_db.all_comp_classes -
                            self.primary_classes)

  def _PreprocessData(self):
    self._BuildReverseVolValueMap()
    self._BuildReverseIcMap()
    self._BuildHwidStatusMaps()
    self._BuildClassSets()
    self.cooked_boms = CookedBoms(self.boms)

  def _EnforceVariantClassesAllMatch(self):
    """Verify that all variants have the same class coverage.

    The set of variant classes are implicitly the set of all possible
    classes, minus those classes used in bom primaries.
    """
    if not self.primary_classes or not self.variants:
      return
    variant_classes = set().union(*[
        ComponentSpecClasses(variant) for variant in self.variants.values()])
    if self.variant_classes != variant_classes:
      missing = self.variant_classes - variant_classes
      extra = ((variant_classes | self.primary_classes) -
               self._comp_db.all_comp_classes)
      msg = ('%r primary and variant classes are incomplete; '
             'primary + variant != all classes' % self.board_name)
      msg += '; missing [%s]' % ', '.join(missing) if missing else ''
      msg += '; extra [%s]' % ', '.join(extra) if extra else ''
      raise Error, msg
    for var_code, variant in self.variants.items():
      if ComponentSpecClasses(variant) != variant_classes:
        raise Error, ('%r variant classes are [%s]; variant %r does not match' %
                      (self.board_name, ', '.join(variant_classes), var_code))

  def _EnforceCompClassesAllMatch(self):
    if not self.primary_classes:
      return
    for bom_name, bom in self.boms.items():
      if ComponentSpecClasses(bom.primary) != self.primary_classes:
        raise Error, ('%r primary classes are [%s]; bom %r does not match' %
                      (self.board_name, ', '.join(self.primary_classes),
                       bom_name))

  def _EnforceVolatileUniqueness(self):
    if len(self.volatile_values) < len(self.reverse_vol_value_map):
      extra = (set(self.reverse_vol_value_map) -
               set(self.volatile_values.values()))
      raise Error, ('volatiles are not all unique; '
                    'volatiles [%s] are redundant' % ', '.join(extra))

  def _EnforceInitialConfigsDontConflict(self):
    for bom_name in self.boms:
      combined_constraints = {}
      for ic_tag in self.reverse_ic_map.get(bom_name, []):
        for key, value in self.initial_configs[ic_tag].constraints.items():
          existing_value = combined_constraints.get(key, None)
          if existing_value is not None and existing_value != value:
            raise Error, ('initial configs for bom %r conflict; enforced '
                          'tags specify more than one differing constraint '
                          'for %r' % (bom_name, key))

  def EnforceInvariants(self):
    self._EnforceVariantClassesAllMatch()
    self._EnforceCompClassesAllMatch()
    self._EnforceVolatileUniqueness()
    self._EnforceInitialConfigsDontConflict()

  def BomExists(self, bom_name):
    if bom_name not in self.boms:
      raise Error, 'unknown bom %r for board %r' % (bom_name, self.board_name)

  def VariantExists(self, var_code):
    if var_code not in self.variants:
      raise Error, ('unknown variant %r for board %r' %
                    (var_code, self.board_name))

  def VolatileExists(self, vol_code):
    if vol_code not in self.volatiles:
      raise Error, ('unknown volatile %r for board %r' %
                    (vol_code, self.board_name))

  def InitialConfigExists(self, ic_code):
    if ic_code not in self.initial_configs:
      raise Error, ('unknown initial_config %r for board %r' %
                    (ic_code, self.board_name))

  def CommonInitialConfigs(self, target_bom_names):
    """Return all initial_config indices shared by the target boms."""
    return set.intersection(*[
        self.reverse_ic_map.get(bom_name, set())
        for bom_name in target_bom_names]) if target_bom_names else set()

  def CommonMissingClasses(self, target_bom_names):
    return set.intersection(*[
        set(self.boms[bom_name].primary.classes_missing)
        for bom_name in target_bom_names]) if target_bom_names else set()

  def CommonDontcareClasses(self, target_bom_names):
    return set.intersection(*[
        set(self.boms[bom_name].primary.classes_dontcare)
        for bom_name in target_bom_names]) if target_bom_names else set()

  def GetVolatileCodes(self, bom_name, variant_code, status_mask):
    variant_status_map = self._hwid_status_map.get(bom_name, {})
    volatile_status_map = variant_status_map.get(variant_code, {})
    return set(volatile_code for volatile_code, status
               in volatile_status_map.items()
               if status in status_mask)

  def SetHwidStatus(self, bom, variant, volatile, status):
    self.UpdateHwidStatusMaps(bom, variant, volatile, status)
    self.UpdateHwidStatusPatterns()
    self._PreprocessData()

  def GetHwidStatus(self, bom_name, variant_code, volatile_code):
    variant_status_map = self._hwid_status_map.get(bom_name, {})
    volatile_status_map = variant_status_map.get(variant_code, {})
    return volatile_status_map.get(volatile_code, None)

  def AvailableBomNames(self, count):
    """Return count random bom names that are not yet used by board."""
    existing_names = set(bom_name for bom_name in self.boms)
    available_names = [bom_name for bom_name in BOM_NAME_SET
                       if bom_name not in existing_names]
    random.shuffle(available_names)
    if len(available_names) < count:
      raise Error('too few available bom names (%d left)' %
                  len(available_names))
    return available_names[:count]

  def CreateBom(self, bom_name, component_spec):
    if bom_name in self.boms:
      raise Error, '%s bom %s already exists' % (self.board_name, bom_name)
    if self.boms:
      existing_primary_classes = set().union(*[
        ComponentSpecClasses(bom.primary) for bom in self.boms.values()])
      new_primary_classes = ComponentSpecClasses(component_spec)
      if new_primary_classes != existing_primary_classes:
        msg = ('proposed bom has different component class '
               'coverage than existing %s boms' % self.board_name)
        missing = existing_primary_classes - new_primary_classes
        if missing:
          msg += ', missing [%s]' % ', '.join(sorted(missing))
        extra = new_primary_classes - existing_primary_classes
        if extra:
          msg += ', extra [%s]' %  ', '.join(sorted(extra))
        raise Error, msg
    bom_data = BomSpec(primary=component_spec, variants=[])
    self.boms[bom_name] = bom_data
    self._PreprocessData()

  def CreateVariant(self, component_spec):
    for existing_var_code, existing_variant in self.variants.items():
      if component_spec.__dict__ == existing_variant.__dict__:
        raise Error, ('%s equivalent variant %s already exists' %
                      (self.board_name, existing_var_code))
    if self.variants:
      variant_classes = set().union(*[
        ComponentSpecClasses(variant) for variant in self.variants.values()])
      if ComponentSpecClasses(component_spec) != variant_classes:
        raise Error, ('proposed variant component data has different class '
                      'coverage than existing %s variants' % self.board_name)
    var_code = AlphaIndex(len(self.variants))
    self.variants[var_code] = component_spec
    self._PreprocessData()
    return var_code

  def AddVolatileValue(self, vol_class, vol_value, vol_name=None):
    if vol_name is None:
      vol_name =  '%s_%d' % (vol_class, len(self.volatile_values))
    Validate.VolatileName(vol_name)
    assert vol_name not in self.volatile_values
    self.volatile_values[vol_name] = vol_value
    self._PreprocessData()
    return vol_name

  def AddVolatile(self, spec):
    vol_tag = AlphaIndex(len(self.volatiles))
    self.volatiles[vol_tag] = spec
    self._PreprocessData()
    return vol_tag

  def AddInitialConfig(self, constraints):
    map(Validate.InitialConfigContraintName, constraints)
    ic = InitialConfigSpec(constraints=constraints, enforced_for_boms=[])
    ic_tag = str(len(self.initial_configs))
    self.initial_configs[ic_tag] = ic
    self._PreprocessData()
    return ic_tag

  def MatchBoms(self, component_data):
    return set(
      bom_name for bom_name, bom in self.boms.items()
      if self._comp_db.MatchComponentSpec(
        bom.primary, component_data.extant_components))

  def MatchVariants(self, bom_name, component_data):
    matches = set()
    bom = self.boms[bom_name]
    for var_code, variant in self.variants.items():
      if var_code not in bom.variants:
        continue
      variant_spec = CombineComponentSpecs(bom.primary, variant)
      if self._comp_db.MatchComponentSpec(variant_spec,
                                          component_data.extant_components):
        matches.add(var_code)
    return matches

  def FmtHwid(self, bom, variant, volatile):
    """Generate HWID string.  See the hwid spec for details."""
    text = '%s %s %s-%s' % (self.board_name, bom, variant, volatile)
    assert text.isupper(), 'HWID cannot have lower case text parts.'
    return str(text + ' ' + HwidChecksum(text))

  def __init__(self, comp_db, board_name, device_data):  # pylint: disable=W0231
    self.__dict__.update(device_data.__dict__)
    self._comp_db = comp_db
    self.board_name = board_name
    self._PreprocessData()
    self.EnforceInvariants()

  @classmethod
  def Read(cls, path, comp_db, board_name):
    full_path = os.path.join(path, board_name)
    if not os.path.isfile(full_path):
      raise InvalidDataError, 'path %r is not a board file' % full_path
    with open(full_path, 'r') as f:
      return cls(comp_db, board_name, DeviceSpec.Decode(f.read()))

  def Write(self, path):
    device_data = DeviceSpec(**dict(
        (field_name, getattr(self, field_name))
        for field_name in DeviceSpec.FieldNames()))
    # Create copy (with known up to date internal data) to re-check invariants.
    Device(self._comp_db, self.board_name, device_data)
    self.WriteOnDiff(path, self.board_name, device_data.Encode())


class HardwareDb(object):

  def __init__(self, path):
    """Read the component_db and all device data files."""
    self._path = path
    self.comp_db = CompDb.Read(path)
    self.devices = dict((entry, Device.Read(path, self.comp_db, entry))
                        for entry in os.listdir(path)
                        if entry.isalpha() and entry.isupper())

  def CreateDevice(self, board_name):
    Validate.BoardName(board_name)
    if board_name in self.devices:
      raise Error, ('board %r already exists' % board_name)
    device = Device(self.comp_db, board_name, DeviceSpec.New())
    self.devices[board_name] = device

  def GetDevice(self, board_name):
    if board_name not in self.devices:
      raise Error, ('board %r does not exist' % board_name)
    return self.devices[board_name]

  def GetHwidData(self, hwid):
    """Return corresponding HwidData for specified HWID string."""
    hwid_parts = ParseHwid(hwid)
    device = self.GetDevice(hwid_parts.board)
    device.BomExists(hwid_parts.bom)
    device.VariantExists(hwid_parts.variant)
    device.VolatileExists(hwid_parts.volatile)
    return HwidData(
      hwid=hwid,
      board_name=hwid_parts.board,
      bom_name=hwid_parts.bom,
      variant_code=hwid_parts.variant,
      volatile_code=hwid_parts.volatile,
      status=device.GetHwidStatus(
        hwid_parts.bom, hwid_parts.volatile, hwid_parts.variant),
      components = CombineComponentSpecs(
        device.boms[hwid_parts.bom].primary,
        device.variants[hwid_parts.variant]),
      initial_config = device.GetInitialConfig(hwid_parts.bom),
      ro_vpds=device.vpd_ro_field_list.copy())

  def Write(self):
    """Write the component_db and all device data files."""
    self.comp_db.Write(self._path)
    for device in self.devices.values():
      device.Write(self._path)


def PrintHwidHierarchy(device, cooked_boms, status_mask):
  """Hierarchically show all details for all specified BOMs.

  Details include both primary and variant component configurations,
  initial config, and status.
  """
  def ShowHwids(depth, bom_name):
    bom = device.boms[bom_name]
    for variant_code in sorted(bom.variants):
      for volatile_code in sorted(device.GetVolatileCodes(
        bom_name, variant_code, status_mask)):
        variant = device.variants[variant_code]
        hwid = device.FmtHwid(bom_name, variant_code, volatile_code)
        status = device.GetHwidStatus(bom_name, variant_code, volatile_code)
        print (depth * '  ') + '%s  [%s]' % (hwid, status)
        for line in FmtRightAlignedDict(variant.components):
          print (depth * '  ') + '  (primary) ' + line
        print ''
  def TraverseBomHierarchy(boms, depth, masks):
    def FmtList(l):
      if len(l) == 1:
        return str(list(l)[0])
      elts = [((depth + 2) * '  ') + str(x) for x in sorted(l)]
      return '\n' + '\n'.join(elts)
    print (depth * '  ') + '-'.join(sorted(boms.names))
    common_ic = device.CommonInitialConfigs(boms.names) - masks.ic
    common_missing = device.CommonMissingClasses(boms.names) - masks.missing
    common_wild = device.CommonDontcareClasses(boms.names) - masks.wild
    common_data = {'initial_config': common_ic,
                   'classes missing': common_missing,
                   'classes dontcare': common_wild}
    common_output = dict((k,  FmtList(v)) for k, v in common_data.items() if v)
    for line in FmtLeftAlignedDict(common_output):
      print (depth * '  ') + '  ' + line
    common_present = dict(
      (comp_class, ', '.join(x for x in (comps - masks.present)))
      for comp_class, comps in boms.comp_map.items()
      if comps - masks.present)
    for line in FmtRightAlignedDict(common_present):
      print (depth * '  ') + '  (primary) ' + line
    print ''
    if len(boms.names) == 1:
      ShowHwids(depth + 1, list(boms.names)[0])
    for sub_boms in boms.hierarchy:
      TraverseBomHierarchy(
        sub_boms,
        depth + 1,
        Obj(ic=masks.ic | common_ic,
            missing = masks.missing | common_missing,
            wild = masks.wild | common_wild,
            present = masks.present | boms.common_comps))
  TraverseBomHierarchy(
    cooked_boms,
    0,
    Obj(ic=set(), present=set(), missing=set(), wild=set()))


# TODO(tammo): Add examples to the command line function docstrings.


@Command('create_device',
         CmdArg('board_name'))
def CreateBoard(config, hw_db):
  """Create a fresh empty device data file with specified board name."""
  hw_db.CreateDevice(config.board_name)


@Command('create_bom',
         CmdArg('-b', '--board', required=True),
         CmdArg('-c', '--comps', nargs='*', default=[]),
         CmdArg('-m', '--missing', nargs='*', default=[]),
         CmdArg('-d', '--dontcare', nargs='*', default=[]),
         CmdArg('--variant_classes', nargs='*', default=[]),
         CmdArg('-n', '--name'))
def CreateBom(config, hw_db):
  device = hw_db.GetDevice(config.board)
  map(hw_db.comp_db.CompExists, config.comps)
  map(hw_db.comp_db.CompClassExists, config.variant_classes)
  if config.variant_classes:
    variant_classes = set(config.variant_classes)
  elif not device.boms:
    raise Error, 'variant classes must be declared for the first bom'
  else:
    variant_classes = hw_db.comp_db.all_comp_classes - device.primary_classes
  if config.missing == ['*'] and config.dontcare == ['*']:
    raise Error, 'missing and dontcase can be simultaneously wildcarded (*)'
  if config.missing == ['*']:
    config.missing = hw_db.comp_db.all_comp_classes - variant_classes
  map(hw_db.comp_db.CompClassExists, config.missing)
  if config.dontcare == ['*']:
    config.dontcare = hw_db.comp_db.all_comp_classes - variant_classes
  map(hw_db.comp_db.CompClassExists, config.dontcare)
  bom_name = config.name if config.name else device.AvailableBomNames(1)[0]
  Validate.BomName(bom_name)
  component_spec = hw_db.comp_db.CreateComponentSpec(
    components=config.comps,
    dontcare=config.dontcare,
    missing=config.missing)
  print 'creating %s bom %s' % (config.board, bom_name)
  device.CreateBom(bom_name, component_spec)


@Command('create_variant',
         CmdArg('-b', '--board', required=True),
         CmdArg('-c', '--comps', nargs='*', default=[]),
         CmdArg('-m', '--missing', nargs='*', default=[]),
         CmdArg('-d', '--dontcare', nargs='*', default=[]))
def CreateVariant(config, hw_db):
  device = hw_db.GetDevice(config.board)
  map(hw_db.comp_db.CompExists, config.comps)
  map(hw_db.comp_db.CompClassExists, config.missing)
  map(hw_db.comp_db.CompClassExists, config.dontcare)
  component_spec = hw_db.comp_db.CreateComponentSpec(
    config.comps, config.missing, config.dontcare)
  variant = device.CreateVariant(component_spec)
  print 'created %s variant %s' % (config.board, variant)


@Command('assign_variant',
         CmdArg('-b', '--board', required=True),
         CmdArg('--bom', required=True),
         CmdArg('--variant', required=True))
def AssignVariant(config, hw_db):
  device = hw_db.GetDevice(config.board)
  device.BomExists(config.bom)
  device.VariantExists(config.variant)
  bom = device.boms[config.bom]
  if config.variant in bom.variants:
    print '%s bom %s already uses variant %s' % (
      config.board, config.bom, config.variant)
  else:
    bom.variants.append(config.variant)
    print 'added variant %s for %s bom %s' % (
      config.board, config.bom, config.variant)


@Command('apply_initial_config',
         CmdArg('-b', '--board', required=True),
         CmdArg('--bom', required=True),
         CmdArg('--ic', required=True),
         CmdArg('--cancel', action='store_true'))
def AssignInitialConfig(config, hw_db):
  device = hw_db.GetDevice(config.board)
  device.BomExists(config.bom)
  Validate.InitialConfigTag(config.ic)
  device.InitialConfigExists(config.ic)
  ic = device.initial_configs[config.ic]
  if config.cancel:
    if config.bom not in ic.enforced_for_boms:
      print 'initial config %s already not enforced for bom %s' % (
        config.ic, config.bom)
    else:
      ic.enforced_for_boms.remove(config.ic)
      print 'not enforcing initial config %s for bom %s' % (
        config.ic, config.bom)
  else:
    if config.bom in ic.enforced_for_boms:
      print 'initial config %s already enforced for bom %s' % (
        config.ic, config.bom)
    else:
      ic.enforced_for_boms.append(config.bom)
      ic.enforced_for_boms.sort()
      print 'enforcing initial config %s for bom %s' % (config.ic, config.bom)


@Command('set_hwid_status',
         CmdArg('-b', '--board', required=True),
         CmdArg('--bom', required=True),
         CmdArg('--variant', required=True),
         CmdArg('--volatile', required=True),
         CmdArg('status'))
def SetHwidStatus(config, hw_db):
  device = hw_db.GetDevice(config.board)
  if config.bom != '*':
    device.BomExists(config.bom)
  if config.variant != '*':
    device.VariantExists(config.variant)
  if config.volatile != '*':
    device.VolatileExists(config.volatile)
  Validate.Status(config.status)
  if not device.boms:
    raise Error, 'cannot assign status, %s has no BOMs' % device.board_name
  if not device.variants:
    raise Error, 'cannot assign status, %s has no variants' % device.board_name
  if not device.volatiles:
    raise Error, 'cannot assign status, %s has no volatiles' % device.board_name
  device.SetHwidStatus(
    config.bom, config.variant, config.volatile, config.status)


@Command('assimilate_data',
         CmdArg('-b', '--board', required=True),
         CmdArg('--create_bom', nargs='?', default=False, metavar='BOM_NAME'))
def AssimilateProbeResults(config, hw_db):
  """Merge new data from stdin into existing data, optionally create a new bom.

  Any new data is added to the hardware database, including component
  probe results, volatile result, and initial_config data.  Canonical
  names are automatically chosen for new data, which can be changed
  later by renaming.

  If a bom name is specified, and if a bom of that name does not
  already exist, attempt to create it, and associate the components
  specified by the input data.  If there is already a bom with the
  exact same component mappings, the request will fail.

  Variant data that cannot be derived from the input data must be
  added to the bom later using other commands.

  Boms created using this command do not have any status, and hence
  there is no binding made with any volatile or initial_config
  properties (including any in the input data).
  """
  device = hw_db.GetDevice(config.board)
  probe_results = ProbeResults.Decode(sys.stdin.read())
  for comp_class in (set(probe_results.found_components) |
                     set(probe_results.missing_component_classes)):
    hw_db.comp_db.CompClassExists(comp_class)
  cooked_results = CookedProbeResults(hw_db.comp_db, device, probe_results)
  for comp in cooked_results.matched_components:
    print 'found matching %r component %r' % (
      hw_db.comp_db.name_class_map[comp], comp)
  for vol_class, vol_name in cooked_results.matched_volatiles.items():
    print 'found matching %r %r volatile %r' % (
      device.board_name, vol_class, vol_name)
  for comp_class, comp_prs in cooked_results.unmatched_components.items():
    for comp_probe_result in comp_prs:
      comp_name = hw_db.comp_db.AddComponent(comp_class, comp_probe_result)
      print 'added component/probe_result %r : %r' % (
        comp_name, comp_probe_result)
  for vol_class, vol_value in cooked_results.unmatched_volatiles.items():
    vol_name = device.AddVolatileValue(vol_class, vol_value)
    print 'added volatile_value/probe_result %r : %r' % (
      vol_name, vol_value)
  if cooked_results.match_tree:
    print '%s matching boms: %s' % (
      'exactly' if cooked_results.component_data_is_complete else 'partially',
      ', '.join(sorted(cooked_results.match_tree)))
  # Cook again, to pick up mappings to added comps/vols.
  cooked_results = CookedProbeResults(
          hw_db.comp_db, device, probe_results)
  if cooked_results.matched_vol_tags:
    print 'matching volatile tags: %s' % ', '.join(
      cooked_results.matched_vol_tags)
  else:
    vol_tag = device.AddVolatile(cooked_results.matched_volatiles)
    print 'added volatile spec as tag %s' % vol_tag
  if cooked_results.matched_ic_tags:
    print 'matching initial config tags: %s' % ', '.join(
      cooked_results.matched_ic_tags)
  else:
    ic_tag = device.AddInitialConfig(cooked_results.initial_configs)
    print 'added initial config spec as tag %s' % ic_tag
    cooked_results.matched_ic_tags = [ic_tag]
  if config.create_bom != False:
    missing_classes = (hw_db.comp_db.all_comp_classes -
                       cooked_results.component_data_classes -
                       device.variant_classes)
    if missing_classes:
      print ('ignoring create_bom argument; component data missing [%s] classes'
             % ', '.join(missing_classes))
      return
    for bom_name in cooked_results.match_tree:
      bom = device.boms[bom_name]
      if bom.primary == cooked_results.matched_components:
        print ('ignoring create_bom argument; identical bom %r already exists' %
               bom_name)
        return
    if config.create_bom in device.boms:
      print ('bom %r exists, but component list differs from this data' %
             config.create_bom)
      return
    bom_name = (config.create_bom if config.create_bom
                else device.AvailableBomNames(1)[0])
    Validate.BomName(bom_name)
    component_spec = hw_db.comp_db.CreateComponentSpec(
      components=cooked_results.matched_components,
      dontcare=set(),
      missing=cooked_results.missing_component_classes)
    print 'creating %s bom %s' % (config.board, bom_name)
    device.CreateBom(bom_name, component_spec)


@Command('hwid_overview',
         CmdArg('--status', nargs='*'),
         CmdArg('-b', '--board'))
def HwidHierarchyViewCommand(config, hw_db):
  """Show HWIDs in visually efficient hierarchical manner.

  Starting with the set of all HWIDs for each board or a selected
  board, show the set of common components and data values, then find
  subsets of HWIDs with maximally shared data and repeat until there
  are only singleton sets, at which point print the full HWID strings.
  """
  map(Validate.Status, config.status if config.status else [])
  status_mask = config.status if config.status else LIFE_CYCLE_STAGES
  for board, device in hw_db.devices.items():
    if config.board:
      if not config.board == board:
        continue
    else:
      print '---- %s ----\n' % board
    PrintHwidHierarchy(device, device.cooked_boms, status_mask)


@Command('hwid_list',
         CmdArg('-b', '--board'),
         CmdArg('-s', '--status', nargs='*'),
         CmdArg('-v', '--verbose', action='store_true',
                help='show status in addition to the HWID string itself'))
def ListHwidsCommand(config, hw_db):
  """Print sorted list of existing HWIDs.

  Optionally list HWIDs for specific status values (default is for all
  HWIDs which have some kind of status to be shown).  Optionally show
  the status of each HWID.  Optionally limit the list to a specific
  board.
  """
  status_mask = config.status if config.status else LIFE_CYCLE_STAGES
  for board, device in hw_db.devices.items():
    if config.board:
      if not config.board == board:
        continue
    filtered_hwid_status_map = dict(
      (hwid, status) for hwid, status in device.flat_hwid_status_map.items()
      if status in status_mask)
    max_hwid_len = (max(len(x) for x in filtered_hwid_status_map)
                    if filtered_hwid_status_map else 0)
    for hwid, status in sorted(filtered_hwid_status_map.items()):
      if config.verbose:
        print '%s%s  [%s]' % (hwid, (max_hwid_len - len(hwid)) * ' ', status)
      else:
        print hwid


@Command('component_breakdown',
         CmdArg('-b', '--board'))
def ComponentBreakdownCommand(config, hw_db):
  """Map components to HWIDs, organized by component.

  For all boards, or for a specified board, first show the set of
  common components.  For all the non-common components, show a list
  of BOM names that use them.
  """
  for board, device in hw_db.devices.items():
    if config.board:
      if not config.board == board:
        continue
    else:
      print '---- %s ----' % board
    common_comp_map = dict(
      (comp_class, ', '.join(comps))
      for comp_class, comps in device.cooked_boms.comp_map.items())
    if common_comp_map:
      print '[common]'
      for line in FmtRightAlignedDict(common_comp_map):
        print '  ' + line
    uncommon_comps = (set(device.cooked_boms.comp_boms_map) -
                      device.cooked_boms.common_comps)
    uncommon_comp_map = {}
    for comp in uncommon_comps:
      comp_class = hw_db.comp_db.name_class_map[comp]
      bom_names = device.cooked_boms.comp_boms_map[comp]
      comp_map = uncommon_comp_map.setdefault(comp_class, {})
      comp_map[comp] = ', '.join(sorted(bom_names))
    for comp_class, comp_map in uncommon_comp_map.items():
      print comp_class + ':'
      for line in FmtRightAlignedDict(comp_map):
        print '  ' + line


@Command('filter_database',
         CmdArg('-b', '--board', required=True),
         CmdArg('-d', '--dest_dir', required=True),
         CmdArg('-s', '--by_status', nargs='*', default=['supported']))
def FilterDatabase(config, data):
  """Generate trimmed down board data file and corresponding component_db.

  Generate a board data file containing only those boms matching the
  specified status, and only that portion of the related board data
  that is used by those boms.  Also produce a component_db which
  contains entries only for those components used by the selected
  boms.
  """
  # TODO(tammo): Validate inputs -- board name, status, etc.
  device = data.devices[config.board]
  target_hwid_map = {}
  target_volatile_set = set()
  target_variant_set = set()
  for bom, hwid in device.hwid_map.items():
    for variant in hwid.variant_list:
      for volatile in device.volatile_map:
        status = device.GetHwidStatus(bom, volatile, variant)
        if status in config.by_status:
          variant_map = target_hwid_map.setdefault(bom, {})
          volatile_list = variant_map.setdefault(variant, [])
          volatile_list.append(volatile)
          target_volatile_set.add(volatile)
          target_variant_set.add(variant)
  filtered_comp_db = CompDb.New()
  filtered_device = Device.New()
  for bom in target_hwid_map:
    hwid = device.hwid_map[bom]
    filtered_hwid = Hwid.New()
    filtered_hwid.component_map = hwid.component_map
    filtered_hwid.variant_list = list(set(hwid.variant_list) &
                                      target_variant_set)
    filtered_device.hwid_map[bom] = filtered_hwid
    for comp_class in hwid.component_map:
      filtered_comp_db.registry[comp_class] = \
          data.comp_db.registry[comp_class]
  for volatile_index in target_volatile_set:
    volatile_details = device.volatile_map[volatile_index]
    filtered_device.volatile_map[volatile_index] = volatile_details
    for volatile_name in volatile_details.values():
      volatile_value = device.volatile_value_map[volatile_name]
      filtered_device.volatile_value_map[volatile_name] = volatile_value
  for variant_index in target_variant_set:
    variant_details = device.variant_map[variant_index]
    filtered_device.variant_map[variant_index] = variant_details
  filtered_device.vpd_ro_field_list = device.vpd_ro_field_list
  WriteDatastore(config.dest_dir,
                 Obj(comp_db=filtered_comp_db,
                     device_db={config.board: filtered_device}))
  # TODO(tammo): Also filter initial_config once the schema for that
  # has been refactored to be cleaner.
  # TODO(tammo): Also filter status for both boms and components once
  # the schema for that has been refactored to be cleaner.


# TODO(tammo): If someone is using this, make it work; otherwise delete.
# @Command('legacy_export',
#          CmdArg('-b', '--board', required=True),
#          CmdArg('-d', '--dest_dir', required=True),
#          CmdArg('-e', '--extra'),
#          CmdArg('-s', '--status', default='supported'))
def LegacyExport(config, data):
  """Generate legacy-format 'components_<HWID>' files.

  For the specified board, in the specified destination directory,
  this will create a hash.db file and one file per HWID.  All of these
  files should be compatible with the pre-hwid-tool era code.

  The goal of this command is to enable maintaining data in the new
  format for use with factory branches that can only consume the older
  format.

  The 'extra' argument can specify a file that contains extra dict
  extries that will be included in each of the hwid files.  This is
  useful for specifying the legacy fields that no longer exist in the
  new data format.

  This command will be removed once we are no longer supporting any
  boards that depend on the old-style data formatting.
  """
  from pprint import pprint
  if config.board not in data.devices:
    print 'ERROR: unknown board %r.' % config.board
    return
  if not os.path.exists(config.dest_dir):
    print 'ERROR: destination directory %r does not exist.' % config.dest_dir
    return
  extra_fields = eval(open(config.extra).read()) if config.extra else None
  device = data.devices[config.board]
  hash_db_path = os.path.join(config.dest_dir, 'hash.db')
  with open(hash_db_path, 'w') as f:
    pprint(device.volatile_value_map, f)
  ic_reverse_map = {}
  for ic_index, bom_list in device.initial_config_use_map.items():
    for bom in bom_list:
      ic_reverse_map[bom] = ic_index
  def WriteLegacyHwidFile(bom, volind, variant, hwid):
    hwid_str = device.FmtHwid(bom, volind, variant)
    export_data = {'part_id_hwqual': [hwid_str]}
    for comp_class, comp_name in hwid.component_map.items():
      if comp_name == 'NONE':
        probe_result = ''
      elif comp_name == 'ANY':
        probe_result = '*'
      else:
        probe_result = data.comp_db.registry[comp_class][comp_name]
      export_data['part_id_' + comp_class] = [probe_result]
    for vol_class, vol_name in device.volatile_map[volind].items():
      export_data['hash_' + vol_class] = [vol_name]
    variant_data = device.variant_map[variant]
    if len(variant_data) not in [0, 1]:
      print ('ERROR: legacy_export expects zero or one variants, '
             'hwid %s has %d.' % (hwid_str, len(variant_data)))
    for variant_value in variant_data:
      export_data['part_id_keyboard'] = [
        data.comp_db.registry['keyboard'][variant_value]]
    initial_config = device.initial_config_map[ic_reverse_map[bom]]
    for ic_class, ic_value in initial_config.items():
      export_data['version_' + ic_class] = [ic_value]
    export_data['config_factory_initial'] = sorted(
        'version_' + ic_class for ic_class in initial_config)
    export_data.update(extra_fields)
    hwid_file_name = ('components ' + hwid_str).replace(' ', '_')
    hwid_file_path = os.path.join(config.dest_dir, hwid_file_name)
    with open(hwid_file_path, 'w') as f:
      pprint(export_data, f)
  for bom, hwid in device.hwid_map.items():
    for volind in device.volatile_map:
      for variant in hwid.variant_list:
        status = device.GetHwidStatus(bom, volind, variant)
        if (config.status != '' and
            (status is None or config.status != status)):
          continue
        WriteLegacyHwidFile(bom, volind, variant, hwid)


@Command('rename_components')
def RenameComponents(config, data):  # pylint: disable=W0613
  """Change canonical component names.

  Given a list of old-new name pairs on stdin, replace each instance
  of each old name with the corresponding new name in the
  component_db and in all board files.  The expected stdin format is
  one pair per line, and the two words in each pair are whitespace
  separated.
  """
  for line in sys.stdin:
    parts = line.strip().split()
    if len(parts) != 2:
      raise Error, ('each line of input must have exactly 2 words, '
                    'found %d [%s]' % (len(parts), line.strip()))
    old_name, new_name = parts
    if old_name not in data.comp_db.name_result_map:
      raise Error, 'unknown canonical component name %r' % old_name
    # TODO(tammo): Validate new_name.
    comp_class = data.comp_db.name_class_map[old_name]
    comp_map = data.comp_db.registry[comp_class]
    probe_result = comp_map[old_name]
    del comp_map[old_name]
    comp_map[new_name] = probe_result
    for device in data.devices.values():
      for hwid in device.hwid_map.values():
        if hwid.component_map.get(comp_class, None) == old_name:
          hwid.component_map[comp_class] = new_name


def Main():
  """Run sub-command specified by the command line args."""
  config = ParseCmdline(
      'Visualize and/or modify HWID and related component data.',
      CmdArg('-p', '--data_path', metavar='PATH',
             default=DEFAULT_HWID_DATA_PATH),
      CmdArg('-l', '--log', metavar='PATH',
             help='Write logs to this file.'),
      verbosity_cmd_arg)
  SetupLogging(config.verbosity, config.log)
  hw_db = HardwareDb(config.data_path)
  try:
    config.command(config, hw_db)
  except Error, e:
    logging.exception(e)
    sys.exit('ERROR: %s' % e)
  except Exception, e:
    logging.exception(e)
    sys.exit('UNCAUGHT RUNTIME EXCEPTION %s' % e)
  hw_db.Write()


if __name__ == '__main__':
  Main()
