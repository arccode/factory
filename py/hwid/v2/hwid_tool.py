#!/usr/bin/env python2
# pylint: disable=E0602,E1101,W0201
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Visualize and/or modify HWID and related component data."""


import copy
import logging
import os
import re
import sys

from itertools import chain
from random import shuffle
from string import uppercase  # pylint: disable=W0402
from zlib import crc32

import factory_common  # pylint: disable=unused-import

from cros.factory.hwid.v2.bom_names import BOM_NAME_SET
from cros.factory.hwid.v2 import yaml_datastore
from cros.factory.hwid.v2.yaml_datastore import InvalidDataError
from cros.factory.hwid.v2.yaml_datastore import YamlDatastore
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils.argparse_utils import verbosity_cmd_arg
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error
from cros.factory.utils.type_utils import Obj


# The expected location of HWID data within a factory image or the
# chroot.
DEFAULT_HWID_DATA_PATH = (
    os.path.join(os.environ['CROS_WORKON_SRCROOT'],
                 'src', 'platform', 'chromeos-hwid', 'v2')
    if sys_utils.InChroot()
    else '/usr/local/factory/hwid')


# File that contains component data shared by all boards.
COMPONENT_DB_FILENAME = 'component_db'

# The size the board and bom name characters.
MAX_BOARD_NAME_SIZE = 9
MAX_BOM_NAME_SIZE = 32

# Regular expression raw strings to match each of HWID component.
BOARD_RE_PATTERN = r'[A-Z]{,%s}' % MAX_BOARD_NAME_SIZE
BOM_RE_PATTERN = r'[A-Z0-9-]{,%s}' % MAX_BOM_NAME_SIZE
VARIANT_RE_PATTERN = r'[A-Z]+'
VOLATILE_RE_PATTERN = r'[A-Z]+'

# Regular expresions to match just BOARD and BOM
BOARD_RE = re.compile(r'^(%s)$' % BOARD_RE_PATTERN)
BOM_RE = re.compile(r'^(%s)$' % BOM_RE_PATTERN)

# Glob-matching for 'BOM VARIANT-VOLATILE' and 'BOARD BOM VARIANT-VOLATILE'.
BVV_GLOB_RE = re.compile(
    r'^(%s)\s+(%s|\*)-(%s|\*)$' %
    (BOM_RE_PATTERN, VARIANT_RE_PATTERN, VOLATILE_RE_PATTERN))
BBVV_GLOB_RE = re.compile(r'^(%s)\s+(%s|\*)\s+(%s|\*)-(%s|\*)$' % (
    BOARD_RE_PATTERN, BOM_RE_PATTERN, VARIANT_RE_PATTERN, VOLATILE_RE_PATTERN))

# HWID regexp.
HWID_RE = re.compile(
    r'^(%s) (%s) (%s)-(%s) ([0-9]+)$' %
    (BOARD_RE_PATTERN, BOM_RE_PATTERN, VARIANT_RE_PATTERN,
     VOLATILE_RE_PATTERN))

# Key to the concatenated probed string in probe results.
COMPACT_PROBE_STR = 'compact_str'

# Possible life cycle stages (status) for components and HWIDs.
LIFE_CYCLE_STAGES = set([
    'supported',
    'qualified',
    'deprecated',
    'eol'])


def MakeDatastoreClass(*args):
  """Define storable object type with a schema and yaml representer.

  This is a warpper for yaml_datastore.MakeDatastoreClass that will bind the new
  class to current module.

  When executed as compiled form (pyc) inside zip (zipimport, par),
  MakeDatastoreClass cannot decode module from stack inspection so we need to
  define the class explicitly here.
  """
  cls = yaml_datastore.MakeDatastoreClass(*args)
  globals()[cls.__name__] = cls


MakeDatastoreClass('StatusData', dict(
    (status_name, (list, str))
    for status_name in LIFE_CYCLE_STAGES))

MakeDatastoreClass('ComponentRegistry', {
    'probeable_components': (dict, (dict, str)),
    'opaque_components': (dict, (list, str)),
    'status': StatusData,
})

# To keep the database more human readable, the below components field
# contains a dict mapping component class to _either_ a single
# component name string for singletons _or_ a list of component name
# strings for when multiple components should exist for a single
# class.  This will allow single line database entries for the many
# singleton cases, only expanding to multi-line lists when there are
# actually multiple entries to track.
MakeDatastoreClass('ComponentSpec', {
    'classes_dontcare': (list, str),
    'classes_missing': (list, str),
    'components': (dict, [str, (list, str)]),
})

# ComponentData is the matching data for ComponentSpec -- in other
# words, ComponentSpec expresses an expectation (including, for
# example, dontcare), whereas ComponentData expresses an actual
# configuration.
MakeDatastoreClass('ComponentData', {
    'classes_missing': (list, str),
    'extant_components': (list, str),
})

MakeDatastoreClass('BomSpec', {
    'primary': ComponentSpec,
    'variants': (list, str),
})

MakeDatastoreClass('InitialConfigSpec', {
    'constraints': (dict, str),
    'enforced_for_boms': (list, str),
})

# TODO(tammo): Consider creating an explicit common-for-all-boms
# component-spec at the device level, to reduce the per-bom noise.
# The contents of this could be derived automatically.
MakeDatastoreClass('DeviceSpec', {
    'boms': (dict, BomSpec),
    'hwid_status': StatusData,
    'initial_configs': (dict, InitialConfigSpec),
    'variants': (dict, ComponentSpec),
    'volatiles': (dict, (dict, str)),
    'volatile_values': (dict, str),
    'vpd_ro_fields': (list, str),
    'vpd_rw_fields': (list, str),
})

MakeDatastoreClass('ProbeResults', {
    'found_probe_value_map': (dict, [(dict, str),
                                     (list, (dict, [str]))]),
    'missing_component_classes': (list, str),
    'found_volatile_values': (dict, [str, (dict, str)]),
    'initial_configs': (dict, str),
})


def HwidChecksum(text):
  return ('%04u' % (crc32(text) & 0xffffffffL))[-4:]


def ParseHwid(hwid):
  """Parse HWID string details.  See the hwid spec for details."""
  match = HWID_RE.findall(hwid)
  if not match:
    raise Error, ('illegal hwid %r, does not match ' % hwid +
                  '"BOARD BOM VARIANT-VOLATILE CHECKSUM" format')
  board, bom, variant, volatile, checksum = match.pop()
  expected_checksum = HwidChecksum(
      '%s %s %s-%s' % (board, bom, variant, volatile))
  if checksum != expected_checksum:
    raise Error, 'bad checksum for hwid %r (expected %s)' % (
        hwid, expected_checksum)
  return Obj(hwid=hwid, board=board, bom=bom,
             variant=variant, volatile=volatile)


def AlphaIndex(num):
  """Generate an alphabetic value corresponding to the input number.

  Translate 0->A, 1->B, .. 25->Z, 26->AA, 27->AB, and so on.
  """
  result = ''
  alpha_count = len(uppercase)
  while True:
    result = uppercase[num % alpha_count] + result
    num /= alpha_count
    if num == 0:
      break
    num -= 1
  return result


def FmtRightAlignedDict(d):
  max_key_width = max(len(k) for k in d) if d else 0
  return ['%s%s: %s' % ((max_key_width - len(k)) * ' ', k, v)
          for k, v in sorted((k, v) for k, v in d.items())]


def FmtLeftAlignedDict(d):
  max_key_width = max(len(k) for k in d) if d else 0
  return ['%s%s: %s' % (k, (max_key_width - len(k)) * ' ', v)
          for k, v in sorted((k, v) for k, v in d.items())]


def ComponentSpecClasses(component_spec):
  """Return full set of component classes referenced anywhere in the spec."""
  return (set(component_spec.classes_dontcare) |
          set(component_spec.classes_missing) |
          set(component_spec.components))


def ComponentSpecClassCompsMap(component_spec):
  """Return comp_class:[comp_name] dict.

  Since the ComponentSpec allows for mappings from component class to
  either lists or singletons, this routine generates a more useful
  dict which converts all singletons to lists of one element.  This
  allows traversal of the datastructure without needing to inspect any
  types.
  """
  return dict(
      (comp_class, comp_data if isinstance(comp_data, list) else [comp_data])
      for comp_class, comp_data in component_spec.components.items())


def ComponentSpecCompClassMap(component_spec):
  """Return comp_name:comp_class dict, for lookup of component class by name."""
  return dict(
      (comp, comp_cls)
      for comp_cls, comps in ComponentSpecClassCompsMap(component_spec).items()
      for comp in comps)


def CombineComponentSpecs(a, b):
  """Return the union of two ComponentSpecs, ignoring any conflicts.

  Creates a new ComponentSpec which is input A with B merged into it,
  meaning that for conflicting component mappings (meaning different
  mappings for a given component class), the result will contain the
  mapping from B (the A mapping gets clobbered).  For dontcare and
  missing, the result contains the unions of the respective component
  class sets.
  """
  components = {}
  components.update(a.components)
  components.update(b.components)
  return ComponentSpec(
      classes_dontcare=list(set(a.classes_dontcare) | set(b.classes_dontcare)),
      classes_missing=list(set(a.classes_missing) | set(b.classes_missing)),
      components=components)


def ComponentSpecsConflict(a, b):
  """Determine if the specs refer to any overlapping classes.

  In other words, determine if combining them would result in any
  conflict (loss of information).
  """
  return (ComponentSpecClasses(a) & ComponentSpecClasses(b)) != set()


def ComponentSpecsEqual(a, b):
  return ((set(a.classes_dontcare) == set(b.classes_dontcare)) and
          (set(a.classes_missing) == set(b.classes_missing)) and
          a.components == b.components)


class Validate(object):  # pylint: disable=W0232

  @classmethod
  def HwidPart(cls, tag, name, matching_re):
    if not matching_re.match(name):
      raise Error, ('%s name %s does not match %s' % (
          tag, name, matching_re.pattern))

  @classmethod
  def BoardName(cls, name):
    cls.HwidPart('board', name, BOARD_RE)

  @classmethod
  def BomName(cls, name):
    cls.HwidPart('bom', name, BOM_RE)

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
        for comp_class, comp_map in self.probeable_components.items()
        for comp_name, probe_result in comp_map.items())

  def _BuildResultNameMap(self):
    self.result_name_map = dict(
        (probe_result, comp_name)
        for comp_class, comp_map in self.probeable_components.items()
        for comp_name, probe_result in comp_map.items())

  def _BuildNameClassMaps(self):
    self.name_class_map = {}
    self.name_class_map.update(dict(
        (comp_name, comp_class)
        for comp_class, comps in self.opaque_components.items()
        for comp_name in comps))
    self.name_class_map.update(dict(
        (comp_name, comp_class)
        for comp_class, comp_map in self.probeable_components.items()
        for comp_name in comp_map))
    self.class_name_map = {}
    for name, comp_class in self.name_class_map.items():
      self.class_name_map.setdefault(comp_class, set()).add(name)

  def _PreprocessData(self):
    self._BuildResultNameMap()
    self._BuildNameResultMap()
    self._BuildNameClassMaps()
    self.all_comp_classes = (set(self.opaque_components) |
                             set(self.probeable_components))
    self.all_comp_names = set(self.name_class_map)
    self.opaque_comp_names = set(
        comp_name
        for comp_class, comps in self.opaque_components.items()
        for comp_name in comps)

  def _EnforceProbeResultUniqueness(self):
    if len(self.result_name_map) < len(self.name_result_map):
      extra = set(self.name_result_map) - set(self.result_name_map.values())
      raise Error, ('probe results are not all unique; '
                    'components [%s] are redundant' % ', '.join(extra))

  def _EnforceCompNameUniqueness(self):
    names = set()
    overlap = set()
    for comp_map in self.probeable_components.values():
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
      comp_map = self.probeable_components.setdefault(comp_class, {})
      comp_map[comp_name] = probe_result
    else:
      self.opaque_components.setdefault(comp_class, []).append(comp_name)
    self._PreprocessData()
    return comp_name

  def __init__(self, data):  # pylint: disable=W0231
    self.__dict__.update(data.__dict__)
    self._PreprocessData()
    self.EnforceInvariants()

  def CreateComponentSpec(self, components=None, dontcare=None, missing=None,
                          filter_component_classes=None):
    """Build spec from a lists of component names and classes.

    This properly builds the ComponentSpec.components mapping (see
    schema documenation) -- create a singleton if there previously was
    nothing, create a list of two elts if there was a singleton, and
    otherwise just add to an existing list.
    """
    components = components if components is not None else []
    dontcare = dontcare if dontcare is not None else []
    missing = missing if missing is not None else []
    comp_map = {}
    for comp in components:
      comp_class = self.name_class_map[comp]
      if filter_component_classes and comp_class in filter_component_classes:
        continue
      comp_data = comp_map.get(comp_class, None)
      if comp_data is None:
        comp_map[comp_class] = comp
      elif isinstance(comp_data, list):
        comp_data.append(comp)
      else:
        comp_map[comp_class] = [comp_data, comp]
    if filter_component_classes:
      missing = list(set(missing) - set(filter_component_classes))
      dontcare = list(set(dontcare) - set(filter_component_classes))
    class_conflict = set(dontcare) & set(missing) & set(comp_map)
    if class_conflict:
      raise Error, ('illegal component specification, conflicting data for '
                    'component classes: %s' % ', '.join(class_conflict))
    return ComponentSpec(
        classes_dontcare=sorted(dontcare),
        classes_missing=sorted(missing),
        components=comp_map)

  def MatchComponentSpecWithData(self, component_spec, component_data,
                                 mismatches=None):
    """Does the specification match the actual configuration data?

    For all extant components check they either match exactly or are
    specified as dontcare.  For all actually missing components, check
    they are specified as either missing or dontcare.

    Args:
      mismatches: If not None, will be populated with a list of reasons why
        the component spec does not match.

    Returns:
      True if the component spec matches.
    """
    if mismatches is None:
      mismatches = []

    spec_class_comps_map = ComponentSpecClassCompsMap(component_spec)
    for comp_class in component_data.classes_missing:
      if comp_class in component_spec.components:
        mismatches.append('component class %s is missing' % comp_class)
    comp_class_to_match = set(component_spec.components.keys())
    comp_class_matched = set()
    for comp in component_data.extant_components:
      comp_class = self.name_class_map[comp]
      if comp_class in component_spec.classes_missing:
        mismatches.append('component class %s should be missing '
                          'but was detected as %s' % (comp_class, comp))
      expected_comps = spec_class_comps_map.get(comp_class, None)
      if expected_comps is not None and comp not in expected_comps:
        mismatches.append('component class %s should be one of %s but was '
                          'detected as %s' % (comp_class, expected_comps, comp))
      # add one item to comp_class_matched
      comp_class_matched.add(comp_class)
    comp_class_not_matched = comp_class_to_match - comp_class_matched
    if len(comp_class_not_matched) != 0:
      mismatches.append('these component classes did not match '
                        'the probed result: %s' %
                        ', '.join(comp_class_not_matched))
    return not mismatches

  def ComponentDataClasses(self, component_data):
    return (set(component_data.classes_missing) |
            set(self.name_class_map[comp]
                for comp in component_data.extant_components))

  def ComponentDataIsComplete(self, component_data):
    return self.ComponentDataClasses(component_data) == self.all_comp_classes

  def MatchComponentProbeValues(self, found_probe_value_map):
    """Resolve component probe results into canonical names.

    Returns the extant_components part of a ComponentData, along with
    a dict of {comp_class:probe_value} for all of the unidentifiable
    components from the input.
    """
    result = Obj(matched=[], unmatched={})
    # Modify HWID v2 to look at COMPACT_PROBE_STR field of probe results.
    for probe_class, pr_data in found_probe_value_map.items():
      if isinstance(pr_data, list):
        probe_values = [pr[COMPACT_PROBE_STR] for pr in pr_data]
      else:
        probe_values = [pr_data[COMPACT_PROBE_STR]]
      for probe_value in probe_values:
        component_name = self.result_name_map.get(probe_value, None)
        if component_name is not None:
          result.matched.append(component_name)
        else:
          pr_list = result.unmatched.setdefault(probe_class, [])
          pr_list.append(probe_value)
    result.matched.sort()
    return result

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
      for comp in ComponentSpecCompClassMap(bom.primary):
        self.comp_boms_map.setdefault(comp, set()).add(bom_name)

  def _BuildCommonCompMap(self):
    """Return (comp_class: [comp]) dict for components common to all boms."""
    self.comp_map = {}
    for bom in self.bom_map.values():
      for comp, comp_class in ComponentSpecCompClassMap(bom.primary).items():
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
      match = BVV_GLOB_RE.findall(pattern)
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
    if not self.boms or not self.variants:
      return
    variant_classes = set().union(*[
        ComponentSpecClasses(variant) for variant in self.variants.values()])
    if self.variant_classes != variant_classes:
      missing = self.variant_classes - variant_classes
      extra = variant_classes - self.variant_classes
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
    """Verify that all boms and variants have the same class coverage.

    Class coverage for boms and variants must be the same to allow
    arbitrary combinations between them.  The set of variant classes
    is implicitly the set of all possible classes minus those classes
    used in bom primaries.

    Also make sure that all classes are known, meaning that they occur
    in the component_db.
    """
    for comp_class in self.primary_classes:
      if comp_class not in self._comp_db.all_comp_classes:
        raise Error, ('%s refers to unknown component class %r' % (
            self.board_name, comp_class))
    for bom_name, bom in self.boms.items():
      if ComponentSpecClasses(bom.primary) != self.primary_classes:
        raise Error, ('%s primary classes are [%s]; bom %r does not match' % (
            self.board_name, ', '.join(self.primary_classes), bom_name))
    for var_code, variant in self.variants.items():
      if ComponentSpecClasses(variant) != self.variant_classes:
        raise Error, ('%s variant classes are [%s]; variant %r does not match' %
                      (self.board_name, ', '.join(self.variant_classes),
                       var_code))

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
    # TODO(tammo): prevent hwid and contained component status conflicts
    # TODO(tammo): for all status values, make sure the corresponding
    # hwid exists ; that the bom has those variant and volatiles
    # assigned

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

  def GetInitialConfigConstraints(self, bom_name):
    constraints = {}
    for ic_code in self.reverse_ic_map.get(bom_name, []):
      constraints.update(self.initial_configs[ic_code].constraints)
    return constraints

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
    shuffle(available_names)
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
          msg += ', extra [%s]' % ', '.join(sorted(extra))
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
      vol_name = '%s_%d' % (vol_class, len(self.volatile_values))
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

  def MatchVolatileValues(self, value_map):
    result = Obj(
        matched_volatiles={},
        unmatched_values={},
        matched_tags=[])
    # Modify HWID v2 to look at COMPACT_PROBE_STR field of probe results.
    for probe_class, pr_data in value_map.items():
      probe_value = pr_data[COMPACT_PROBE_STR]
      volatile_name = self.reverse_vol_value_map.get(probe_value, None)
      if volatile_name is not None:
        result.matched_volatiles[probe_class] = volatile_name
      else:
        result.unmatched_values[probe_class] = probe_value
    result.matched_tags = sorted(
        tag for tag, volatile in self.volatiles.items()
        if (volatile == result.matched_volatiles
            or not volatile))
    return result

  def MatchInitialConfigValues(self, value_map):
    return sorted(
        tag for tag, ic in self.initial_configs.items()
        if ic.constraints == value_map)

  def MatchBoms(self, component_data):
    ret = set()
    for bom_name, bom in self.boms.items():
      mismatches = []
      if self._comp_db.MatchComponentSpecWithData(bom.primary, component_data,
                                                  mismatches):
        ret.add(bom_name)
      else:
        logging.debug('%s does not match: ', bom_name)
        for m in mismatches:
          logging.debug('  - %s', m)
    return ret

  def MatchVariants(self, bom_name, component_data):
    matches = set()
    bom = self.boms[bom_name]
    for var_code, variant in self.variants.items():
      if var_code not in bom.variants:
        continue
      variant_spec = CombineComponentSpecs(bom.primary, variant)
      if self._comp_db.MatchComponentSpecWithData(variant_spec, component_data):
        matches.add(var_code)
    return matches

  def BuildMatchTree(self, component_data, volatile_tags=None):
    """Return nesting dicts with matches for component and volatile data.

    Tree looks like {bom_name: {var_code: {vol_code: (hwid,
    status)}}}, containing those boms that match the component_data,
    then for those boms the variants that match the component_data,
    and finally those volatiles that match the specified set of tags
    and also have non-None status.
    """
    volatile_tags = volatile_tags if volatile_tags is not None else []
    match_tree = dict((bom_name, {}) for bom_name in
                      self.MatchBoms(component_data))
    for bom_name, variant_tree in match_tree.items():
      matching_variants = self.MatchVariants(bom_name, component_data)
      for var_code in matching_variants:
        volatile_tree = variant_tree.setdefault(var_code, {})
        for vol_tag in volatile_tags:
          status = self.GetHwidStatus(bom_name, var_code, vol_tag)
          if status is not None:
            volatile_tree[vol_tag] = status
    return match_tree

  def GetMatchTreeHwids(self, match_tree):
    """Return a {hwid: status} dict built from a MatchTree."""
    return dict(
        (self.FmtHwid(bom_name, variant_code, volatile_code), status)
        for bom_name, variant_tree in match_tree.items()
        for variant_code, volatile_tree in variant_tree.items()
        for volatile_code, status in volatile_tree.items())

  def IntersectBomsAndInitialConfigs(self, initial_config_tags):
    """Return bom_name list for which specified initial_configs are enforced."""
    return set(
        bom_name for bom_name in self.boms
        if set(self.reverse_ic_map.get(bom_name, [])) <= set(
            initial_config_tags))

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
    self.path = path
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
    return device

  def GetDevice(self, board_name=None):
    if board_name is None and len(self.devices) == 1:
      return self.devices[self.devices.keys().pop()]
    if board_name not in self.devices:
      raise Error, ('board %r does not exist' % board_name)
    return self.devices[board_name]

  def Write(self):
    """Write the component_db and all device data files."""
    self.comp_db.Write(self.path)
    for device in self.devices.values():
      device.Write(self.path)


def PrintHwidHierarchy(device, cooked_boms, status_mask):
  """Hierarchically show all details for all specified BOMs.

  Details include both primary and variant component configurations,
  initial config, and status.
  """
  def FmtList(depth, l):
    if len(l) == 1:
      return str(list(l)[0])
    elts = [((depth + 2) * '  ') + str(x) for x in sorted(l)]
    return '\n' + '\n'.join(elts)

  def ShowHwids(depth, bom_name):
    bom = device.boms[bom_name]
    for variant_code in sorted(bom.variants):
      for volatile_code in sorted(device.GetVolatileCodes(
          bom_name, variant_code, status_mask)):
        variant = device.variants[variant_code]
        hwid = device.FmtHwid(bom_name, variant_code, volatile_code)
        status = device.GetHwidStatus(bom_name, variant_code, volatile_code)
        print (depth * '  ') + '%s  [%s]' % (hwid, status)
        variant_comps = (
            dict(
                (comp_class, ', '.join(comps))
                for comp_class, comps in
                ComponentSpecClassCompsMap(variant).items()))
        for line in FmtRightAlignedDict(variant_comps):
          print (depth * '  ') + '  (variant) ' + line
        extra_class_data = {'classes missing': variant.classes_missing,
                            'classes dontcare': variant.classes_dontcare}
        extra_class_output = dict(
            (k, FmtList(depth, v)) for k, v in extra_class_data.items() if v)
        for line in FmtLeftAlignedDict(extra_class_output):
          print (depth * '  ') + '  ' + line
        print ''

  def TraverseBomHierarchy(boms, depth, masks):
    print (depth * '  ') + '-'.join(sorted(boms.names))
    common_ic = device.CommonInitialConfigs(boms.names) - masks.ic
    common_missing = device.CommonMissingClasses(boms.names) - masks.missing
    common_wild = device.CommonDontcareClasses(boms.names) - masks.wild
    common_data = {'initial_config': common_ic,
                   'classes missing': common_missing,
                   'classes dontcare': common_wild}
    common_output = dict(
        (k, FmtList(depth, v)) for k, v in common_data.items() if v)
    for line in FmtLeftAlignedDict(common_output):
      print (depth * '  ') + '  ' + line
    common_present = dict(
        (comp_class, ', '.join(x for x in comps - masks.present))
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
              missing=masks.missing | common_missing,
              wild=masks.wild | common_wild,
              present=masks.present | boms.common_comps))
  TraverseBomHierarchy(
      cooked_boms,
      0,
      Obj(ic=set(), present=set(), missing=set(), wild=set()))


# TODO(tammo): Add examples to the command line function docstrings.


@Command('create_device',
         CmdArg('board_name'))
def CreateBoard(config, hw_db):
  """Create empty device data file for specified board."""
  hw_db.CreateDevice(config.board_name)


@Command(
    'create_bom', CmdArg('-b', '--board', required=True),
    CmdArg(
        '-c', '--comps', nargs='*', default=[],
        help='list of component names'),
    CmdArg(
        '-m', '--missing', nargs='*', default=[],
        help='list of component classes, or "*"'),
    CmdArg(
        '-d', '--dontcare', nargs='*', default=[],
        help='list of component classes, or "*"'),
    CmdArg(
        '--variant_classes', nargs='*', default=[],
        help='list of component classes'),
    CmdArg(
        '-n', '--name',
        help='optional bom name; '
             'will be automatically provided if not specified'))
def CreateBom(config, hw_db):
  """Create a new bom with specified components.

  Either --missing or --dontcare can optionally be passed '*' to
  indicate all components are either missing or always-matched.

  The '*' wildcard will automatically cover all non-variant component
  classes for the specified board.  Correspondingly, if this is the
  first bom for the board, then you likely also want to specify
  --variant_classes to explicitly enunerate which classes will be
  covered by variants (and should not be included in the missing or
  dontcare sets).

  If no name is specified for the new bom, a name will be
  automatically provided from a pool of unused bom names.
  """
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
    raise Error, 'missing and dontcase cannot be simultaneously wildcarded (*)'
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


@Command(
    'create_bom_matrix', CmdArg('-b', '--board', required=True),
    CmdArg(
        '--cross_comps', nargs='*', default=[],
        help='list of component names'),
    CmdArg(
        '--fixed_comps', nargs='*', default=[],
        help='list of component names'),
    CmdArg(
        '-m', '--missing', nargs='*', default=[],
        help='list of component classes'),
    CmdArg(
        '-d', '--dontcare', nargs='*', default=[],
        help='list of component classes'))
def CreateBomMatrix(config, hw_db):
  """Create all possible boms from the specified components.

  Enough components need to be specified to avoid any ambiguity in
  component configurations.  Specifically, component class coverage
  must be complete.  To make this as easy as possible, this command
  will assume that any component classes not specified on the command
  line should match the bindings of existing boms.  If there are no
  existing boms, or if the existing boms do not all have exactly the
  same component bindings for the classes in question, this will fail.
  In other words, it is necessary to specify components on the command
  line for all component classes that do not share common mappings
  across all existing boms.

  NOTE: This routine will only assign a single component per component
  class, and hence is not useful for creating boms where more than one
  component should be present for a single component class.

  Example:

  // Create all of the 18 boms possible with 3 cpus, 3 tpms, and 2 keyboards:
  create_bom_matrix -b FOO --missing %s --cross_comps cpu_0 \
    cpu_1 cpu_2 tpm_0 tpm_1 tpm_2 kbd_0 kbd_1
  """
  def DoCrossproduct(target_comps_list, accumulator=[]):  # pylint: disable=W0102
    return (list(chain.from_iterable(
        [DoCrossproduct(target_comps_list[1:], accumulator + [comp])
         for comp in target_comps_list[0]]))
            if target_comps_list else [accumulator])
  comp_db = hw_db.comp_db
  device = hw_db.GetDevice(config.board)
  map(comp_db.CompExists, config.cross_comps)
  map(comp_db.CompExists, config.fixed_comps)
  map(comp_db.CompClassExists, config.dontcare)
  map(comp_db.CompClassExists, config.missing)
  fixed_component_spec = comp_db.CreateComponentSpec(
      components=config.fixed_comps,
      dontcare=config.dontcare,
      missing=config.missing)
  common_component_spec = comp_db.CreateComponentSpec(
      components=device.cooked_boms.common_comps,
      filter_component_classes=ComponentSpecClasses(fixed_component_spec))
  fixed_component_spec = CombineComponentSpecs(
      fixed_component_spec, common_component_spec)
  print 'fixed component spec:\n%s' % fixed_component_spec.Encode()
  cross_component_spec = comp_db.CreateComponentSpec(
      components=config.cross_comps)
  cross_class_comps_map = ComponentSpecClassCompsMap(cross_component_spec)
  total_classes = (ComponentSpecClasses(fixed_component_spec) |
                   set(cross_class_comps_map))
  if total_classes != device.primary_classes:
    raise Error, ('component specification insufficient, also need '
                  'specification for component classes: %s' %
                  ', '.join(sorted(device.primary_classes - total_classes)))
  crossproduct = DoCrossproduct(cross_class_comps_map.values())
  target_component_specs = []
  for comps in crossproduct:
    component_spec = comp_db.CreateComponentSpec(components=comps)
    component_spec = CombineComponentSpecs(fixed_component_spec, component_spec)

    # pylint:disable=cell-var-from-loop
    def Unique((bom_name, bom)):
      if not ComponentSpecsEqual(component_spec, bom.primary):
        return True
      print 'existing bom matches one config: %s' % bom_name
    if not all(map(Unique, device.boms.items())):
      continue
    target_component_specs.append(component_spec)
  print 'creating %d new boms\n' % len(target_component_specs)
  bom_names = device.AvailableBomNames(len(target_component_specs))
  for bom_name, component_spec in zip(bom_names, target_component_specs):
    print bom_name
    print component_spec.Encode()
    device.CreateBom(bom_name, component_spec)


@Command(
    'create_variant', CmdArg('-b', '--board', required=True),
    CmdArg(
        '-c', '--comps', nargs='*', default=[],
        help='list of component names'),
    CmdArg(
        '-m', '--missing', nargs='*', default=[],
        help='list of component classes'),
    CmdArg(
        '-d', '--dontcare', nargs='*', default=[],
        help='list of component classes'))
def CreateVariant(config, hw_db):
  """Create a new variant with specified components.

  For the specified board, create a new variant from given compontent
  specs.

  Examples:

  // Create board FOO variant for the 'logitec_us_ext' keyboard.
  create_variant -b FOO -c logitec_ex_ext

  // Create an empty variant for board FOO.
  create_variant -b FOO

  // Create a variant that matches all possible keyboard for board FOO.
  create_variant -b FOO --dontcare keyboard
  """
  device = hw_db.GetDevice(config.board)
  map(hw_db.comp_db.CompExists, config.comps)
  map(hw_db.comp_db.CompClassExists, config.missing)
  map(hw_db.comp_db.CompClassExists, config.dontcare)
  component_spec = hw_db.comp_db.CreateComponentSpec(
      config.comps, config.dontcare, config.missing)
  variant = device.CreateVariant(component_spec)
  print 'created %s variant %s' % (config.board, variant)


@Command('assign_variant',
         CmdArg('-b', '--board', required=True),
         CmdArg('--bom', required=True),
         CmdArg('--variant', required=True))
# TODO(tammo): Make --bom into a list --boms and assign to all.
def AssignVariant(config, hw_db):
  """Associate variant with bom."""
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
  """Start or cancel initial config enforcement.

  Make sure that the specified initial_config is enforced for the
  specified board-bom combination.  Unless --cancel is specified, in
  which case any matching enforcement is terminated.
  """
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
         CmdArg('pattern'),
         CmdArg('status'))
def SetHwidStatus(config, hw_db):
  """(Re)Assign status to HWIDs.

  Set the status for a single HWID or for a group of HWIDs specified
  using '*'-based glob expressions over BOM, VARIANT, and VOLATILE
  fields.  The '*' value implies all possible values for the
  corresponding field.

  For all of the affected HWIDs, their status will be reset as
  specified.  This will clobber any existing status, if any.

  Examples:

  // This sets supported status for all variants of device FOO bom BAR
  // with volatile code X.
  set_hwid_status 'FOO BAR *-X' supported

  // This sets 'eol' status just for 'FOO BAR A-B'
  set_hwid_status 'FOO BAR A-B' eol

  // This sets 'deprecated' status for all FOO boms and variants with
  // volatile code C.
  set_hwid_status 'FOO * *-C' deprecated
  """
  match = BBVV_GLOB_RE.findall(config.pattern)
  if not match:
    raise Error, ('illegal input pattern %r, expected '
                  'BOARD BOM VARIANT-VOLATILE' % config.pattern)
  board, bom, variant, volatile = match.pop()
  device = hw_db.GetDevice(board)
  if bom != '*':
    device.BomExists(bom)
  if variant != '*':
    device.VariantExists(variant)
  if volatile != '*':
    device.VolatileExists(volatile)
  Validate.Status(config.status)
  if not device.boms:
    raise Error, 'cannot assign status, %s has no BOMs' % device.board_name
  if not device.variants:
    raise Error, 'cannot assign status, %s has no variants' % device.board_name
  if not device.volatiles:
    raise Error, 'cannot assign status, %s has no volatiles' % device.board_name
  device.SetHwidStatus(bom, variant, volatile, config.status)


@Command('assimilate_data',
         CmdArg('-b', '--board', required=True),
         CmdArg('--create_bom', nargs='?', default=False, metavar='BOM_NAME'))
def AssimilateProbeResults(config, hw_db):
  """Merge new data from stdin, optionally create new bom.

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
  for comp_class in (set(probe_results.found_probe_value_map) |
                     set(probe_results.missing_component_classes)):
    hw_db.comp_db.CompClassExists(comp_class)
  cooked_components = hw_db.comp_db.MatchComponentProbeValues(
      probe_results.found_probe_value_map)
  for comp in cooked_components.matched:
    print 'found matching %r component %r' % (
        hw_db.comp_db.name_class_map[comp], comp)
  for comp_class, comp_prs in cooked_components.unmatched.items():
    for comp_probe_result in comp_prs:
      comp_name = hw_db.comp_db.AddComponent(comp_class, comp_probe_result)
      print 'added component/probe_result %r : %r' % (
          comp_name, comp_probe_result)
  cooked_volatiles = device.MatchVolatileValues(
      probe_results.found_volatile_values)
  for vol_class, vol_name in cooked_volatiles.matched_volatiles.items():
    print 'found matching %r %r volatile %r' % (
        device.board_name, vol_class, vol_name)
  for vol_class, vol_value in cooked_volatiles.unmatched_values.items():
    vol_name = device.AddVolatileValue(vol_class, vol_value)
    print 'added volatile_value/probe_result %r : %r' % (
        vol_name, vol_value)
  cooked_initial_configs = device.MatchInitialConfigValues(
      probe_results.initial_configs)
  if cooked_initial_configs:
    print 'matching initial config tags: %s' % ', '.join(cooked_initial_configs)
  else:
    ic_tag = device.AddInitialConfig(probe_results.initial_configs)
    print 'added initial config spec as tag %s' % ic_tag
  # Cook components and volatiles again, to pick up new mappings.
  recooked_components = hw_db.comp_db.MatchComponentProbeValues(
      probe_results.found_probe_value_map)
  component_data = ComponentData(
      extant_components=recooked_components.matched,
      classes_missing=probe_results.missing_component_classes)
  recooked_volatiles = device.MatchVolatileValues(
      probe_results.found_volatile_values)
  if recooked_volatiles.matched_tags:
    print 'matching volatile tags: %s' % ', '.join(
        recooked_volatiles.matched_tags)
  else:
    vol_tag = device.AddVolatile(recooked_volatiles.matched_volatiles)
    print 'added volatile spec as tag %s' % vol_tag
  match_tree = device.BuildMatchTree(
      component_data, recooked_volatiles.matched_tags)
  if match_tree:
    is_complete = hw_db.comp_db.ComponentDataIsComplete(component_data)
    print '%s matching boms: %s' % (
        'exactly' if is_complete else 'partially', ', '.join(
            sorted(match_tree)))
  if config.create_bom != False:
    missing_classes = (
        hw_db.comp_db.all_comp_classes - device.variant_classes -
        hw_db.comp_db.ComponentDataClasses(component_data))
    if missing_classes:
      print ('ignoring create_bom argument; component data missing [%s] classes'
             % ', '.join(missing_classes))
      return
    component_spec = hw_db.comp_db.CreateComponentSpec(
        components=recooked_components.matched,
        missing=component_data.classes_missing,
        filter_component_classes=device.variant_classes)
    for bom_name in match_tree:
      bom = device.boms[bom_name]
      if bom.primary == component_spec.components:
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
    print 'creating %s bom %s' % (config.board, bom_name)
    device.CreateBom(bom_name, component_spec)


# TODO(tammo): add_component and set_component_status commands


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


@Command('hwid_list_csv',
         CmdArg('-b', '--board'),
         CmdArg('-s', '--status', nargs='*'))
def ListHwidsCSVCommand(config, hw_db):
  """Print sorted list of existing HWIDs as CSV format.

  Optionally list HWIDs for specific status values (default is for all
  HWIDs which have some kind of status to be shown).
  """
  status_mask = config.status if config.status else LIFE_CYCLE_STAGES
  for board, device in hw_db.devices.iteritems():
    if config.board:
      if not config.board == board:
        continue
    filtered_hwid_map = (
        dict(
            (hwid, status)
            for hwid, status in device.flat_hwid_status_map.iteritems()
            if status in status_mask))

    # Prepare CSV header
    header = ['hwid']
    var_header = []
    for var_code in device.variants:
      var_header = sorted(device.variants[var_code].classes_missing +
                          device.variants[var_code].components.keys())
      break

    # Because variant of BOMs are the same, so we generate each variant first.
    # Components described in classes_missing and components, we add these
    # components into tmp_dict first and sort tmp_dict to make output
    # consistently.
    var_comps_dict = {}
    for var_code in device.variants:
      var_comps_dict[var_code] = []
      tmp_dict = copy.copy(device.variants[var_code].components)
      # For missing class, shows 'None'
      for comp_class in device.variants[var_code].classes_missing:
        tmp_dict[comp_class] = 'None'
      for comp_class, comps in sorted(tmp_dict.iteritems()):
        var_comps_dict[var_code].append(comps)

    # For each bom combination, output components composition
    for bom_name, bom in sorted(device.boms.iteritems()):
      # Output header at once, primary components first and then variant
      # components
      if len(header) == 1:
        for comp_class, comps in sorted(bom.primary.components.iteritems()):
          header.append(comp_class)
        header += var_header
        print ','.join(header)

      for var_code in bom.variants:
        for vol_code in device.volatiles:
          hwid = device.FmtHwid(bom_name, var_code, vol_code)
          if hwid in filtered_hwid_map:
            comp_list = []
            # Find out components for this hwid and add variant components
            for comp_class, comps in sorted(bom.primary.components.iteritems()):
              if isinstance(comps, list):
                comp_list.append(' '.join(comps))
              else:
                comp_list.append(comps)
            comp_list += var_comps_dict[var_code]
            print '%s,%s' % (hwid, ','.join(comp_list))


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
         CmdArg('-d', '--dest_dir'),
         CmdArg('-s', '--status', nargs='*', default=['supported']))
def FilterDatabase(config, hw_db):
  """Filter board and component_db files based on status.

  Generate a board data file containing only those boms matching the
  specified status, and only that portion of the related board data
  that is used by those boms.  Also produce a component_db which
  contains entries only for those components used by the selected
  boms.

  If dest_dir is not specified, a subdirectory of the current database
  directory will automatically be created with the name
  'filtered_db_BOARD', for the corresponding board name.
  """
  device = hw_db.GetDevice(config.board)
  if not config.dest_dir:
    config.dest_dir = os.path.join(hw_db.path, 'filtered_db_' + config.board)
    if not os.path.isdir(config.dest_dir):
      os.mkdir(config.dest_dir)
  elif not os.path.isdir(config.dest_dir):
    raise Error, ('target directory %r does not exist' % config.dest_dir)
  map(Validate.Status, config.status)
  target_status = {}
  target_hwids = set()
  target_boms = set()
  target_variants = set()
  target_volatiles = set()
  for hwid, status in device.flat_hwid_status_map.items():
    parsed_hwid = ParseHwid(hwid)
    if status not in config.status:
      continue
    target_hwids.add(parsed_hwid)
    target_boms.add(parsed_hwid.bom)
    target_variants.add(parsed_hwid.variant)
    target_volatiles.add(parsed_hwid.volatile)
    target_status.setdefault(status, []).append(parsed_hwid)
  target_components = (
      set(comp for comp, boms in device.cooked_boms.comp_boms_map.items()
          if target_boms & boms) |
      set(comp
          for var_code in target_variants
          for comp in ComponentSpecCompClassMap(device.variants[var_code])))
  target_volatile_names = set(
      vol_name
      for vol_code in target_volatiles
      for vol_name in device.volatiles[vol_code].values())
  comp_db = hw_db.comp_db
  filtered_comp_db = CompDb(ComponentRegistry(
      probeable_components=dict(
          (comp_class, dict(
              (comp_name, probe_result)
              for comp_name, probe_result in comp_map.items()
              if comp_name in target_components))
          for comp_class, comp_map in comp_db.probeable_components.items()),
      opaque_components=dict(
          (comp_class, [comp_name for comp_name in comps
                        if comp_name in target_components])
          for comp_class, comps in comp_db.opaque_components.items()),
      status=StatusData(**dict(
          (status, [comp_name for comp_name in getattr(comp_db.status, status)
                    if comp_name in target_components])
          for status in LIFE_CYCLE_STAGES))))
  filtered_device = Device(filtered_comp_db, config.board, DeviceSpec(
      boms=dict((bom_name, bom) for bom_name, bom in device.boms.items()
                if bom_name in target_boms),
      hwid_status=StatusData(**dict(
          (status, ['%s %s-%s' % (hwid.bom, hwid.variant, hwid.volatile)
                    for hwid in target_status.get(status, set())])
          for status in LIFE_CYCLE_STAGES)),
      initial_configs=dict(
          (ic_tag, InitialConfigSpec(
              constraints=ic.constraints,
              enforced_for_boms=list(set(ic.enforced_for_boms) & target_boms)))
          for ic_tag, ic in device.initial_configs.items()
          if set(ic.enforced_for_boms) & target_boms),
      variants=dict((var_code, device.variants[var_code])
                    for var_code in target_variants),
      volatiles=dict((vol_code, vol_spec)
                     for vol_code, vol_spec in device.volatiles.items()
                     if vol_code in target_volatiles),
      volatile_values=dict((vol_name, device.volatile_values[vol_name])
                           for vol_name in target_volatile_names),
      vpd_ro_fields=device.vpd_ro_fields,
      vpd_rw_fields=device.vpd_rw_fields))
  filtered_comp_db.Write(config.dest_dir)
  filtered_hw_db = HardwareDb(config.dest_dir)
  filtered_hw_db.devices[config.board] = filtered_device
  filtered_hw_db.Write()


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
  from pprint import pprint  # pylint: disable=W0404
  if config.board not in data.devices:
    print 'ERROR: unknown board %r.' % config.board
    return
  if not os.path.exists(config.dest_dir):
    print 'ERROR: destination directory %r does not exist.' % config.dest_dir
    return
  # pylint: disable=eval-used
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
def RenameComponents(config, hw_db):  # pylint: disable=W0613
  """Change canonical component names.

  Given a list of old-new name pairs on stdin, replace each instance
  of each old name with the corresponding new name in the
  component_db and in all board files.  The expected stdin format is
  one pair per line, and the two words in each pair are whitespace
  separated.
  """
  pairs = [line.strip().split() for line in sys.stdin]
  comp_db = hw_db.comp_db
  for pair in pairs:
    if len(pair) != 2:
      raise Error, ('each line of input must have exactly 2 words, '
                    'found line with %r' % pair)
    old_name, new_name = pair
    Validate.ComponentName(new_name)
    comp_db.CompExists(old_name)
  for old_name, new_name in pairs:
    comp_class = comp_db.name_class_map[old_name]
    if old_name in comp_db.opaque_comp_names:
      comps = comp_db.opaque_components[comp_class]
      comps.remove(old_name)
      comps.append(new_name)
    else:
      comp_map = comp_db.probeable_components[comp_class]
      comp_map[new_name] = comp_map.pop(old_name)

    def UpdateComponentSpec(spec):
      for comp_class, comp_data in spec.components.items():
        if isinstance(comp_data, list) and old_name in comp_data:
          comp_data.remove(old_name)
          comp_data.append(new_name)
        elif comp_data == old_name:
          spec.components[comp_class] = new_name
    for device in hw_db.devices.values():
      for bom in device.boms.values():
        UpdateComponentSpec(bom.primary)
      for variant in device.variants.values():
        UpdateComponentSpec(variant)


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
  except Error as e:
    logging.exception(e)
    sys.exit('ERROR: %s' % e)
  except Exception as e:
    logging.exception(e)
    sys.exit('UNCAUGHT RUNTIME EXCEPTION %s' % e)
  hw_db.Write()


if __name__ == '__main__':
  Main()
