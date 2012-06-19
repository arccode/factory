#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Visualize and/or modify HWID and related component data."""


import logging
import os
import random
import re
import string
import sys
import zlib

from bom_names import BOM_NAME_SET
from common import Error, Obj, SetupLogging, YamlWrite, YamlRead
from hacked_argparse import CmdArg, Command, ParseCmdline, verbosity_cmd_arg
from yaml_datastore import InvalidDataError, MakeDatastoreClass, YamlDatastore


# The expected location of HWID data within a factory image.
DEFAULT_HWID_DATA_PATH = '/usr/local/factory/hwid'


# File that contains component data shared by all boards.
COMPONENT_DB_FILENAME = 'component_db'


# Glob-matching for 'BOM VARIANT-VOLATILE' regexp.
HWID_GLOB_RE = re.compile(r'^([A-Z]+|\*) ([A-Z]+|\*)-([A-Z]+|\*)$')


# Possible life cycle stages (status) for components and HWIDs.
LIFE_CYCLE_STAGES = [
    'supported',
    'qualified',
    'deprecated',
    'eol']


MakeDatastoreClass('XCompData', {
    'registry': (dict, (dict, str)),
    'status_map': (dict, (dict, str)),
    })

MakeDatastoreClass('XHwid', {
    'component_map': (dict, str),
    'variant_list': (list, str),
    })

MakeDatastoreClass('XDevice', {
    'hwid_map': (dict, XHwid),
    'hwid_status_map': (dict, (list, str)),
    'initial_config_map': (dict, (dict, str)),
    'initial_config_use_map': (dict, (list, str)),
    'variant_map': (dict, (list, str)),
    'volatile_map': (dict, (dict, str)),
    'volatile_value_map': (dict, str),
    'vpd_ro_field_list': (list, str),
     })


MakeDatastoreClass('StatusData', dict(
    (status_name, (list, str))
    for status_name in LIFE_CYCLE_STAGES))

MakeDatastoreClass('ComponentRegistry', {
    'components': (dict, (dict, str)),
    'status': StatusData,
    })

MakeDatastoreClass('ComponentData', {
    'classes_dontcare': (list, str),
    'classes_missing': (list, str),
    'components': (dict, [str, (list, str)]),
    })

MakeDatastoreClass('BomData', {
    'primary': ComponentData,
    'variants': (list, str),
    })

MakeDatastoreClass('InitialConfigData', {
    'constraints': (dict, str),
    'enforced_for_boms': (list, str),
    })

MakeDatastoreClass('DeviceData', {
    'boms': (dict, BomData),
    'hwid_status': StatusData,
    'initial_configs': (dict, InitialConfigData),
    'variants': (dict, ComponentData),
    'volatiles': (dict, (dict, str)),
    'volatile_values': (dict, str),
    'vpd_ro_fields': (list, str),
    })


# TODO(tammo): Add invariant checking!

# TODO(tammo): Maintain the invariant that the set of component
# classes in the component_db matches the set of component classes in
# all boms, and also matches the set output by the probing code.

# TODO(tammo): Variant data should have 'probe results' stored in the
# component_db, and the variant_map should only contain a list of
# canonical component names.  Based on the component classes that
# occur in the variant_map, automatically derive a set of components
# that are 'secondary' and make sure these components never appear in
# any Hwid component_map.  Basically, the variant data should be a top
# level datapoint that feeds into creating per-hwid component_maps.
# Calculations on hwids should use these unified (bom+variant)
# component maps.

# TODO(tammo): The hwid_status_map should support some kind of more
# obvious glob syntax -- the current bom-volatile is counterintuitive
# since it does not match the hwid string field order, and also not
# very flexible.  Make sure to add proper sanity checking invariants
# -- for example to make sure each hwid has only one status.

# TODO(tammo): The initial_config_use_map should support glob matching
# similar to the hwid_status_map, this would allow boms to have
# different initial_config depending on their volatile setting.

# TODO(tammo): Fix initial config to have canonical names for each
# 'probe result', stored as a map in device.

# TODO(tammo): Enforce that volatile canonical names (the keys in the
# volatile_value_map) are all lower case, to allow for the special
# 'ANY' tag.  Or not ... this might be worth some thought; volatile
# must always be a perfect match, so there should either be a value or
# nothing?

# TODO(tammo): For those routines that take 'data' as the first arg,
# consider making them methods of a DeviceDb class and then have the
# constructor for that class read the data from disk.

# TODO(tammo): Refactor code to lift out the command line tool parts
# from the core functionality of the module.  Goal is that the key
# operations should be accessible with a meaningful programmatic API,
# and the command line tool parts should just be one of the clients of
# that API.

# TODO(tammo): Make sure that command line commands raise Error for
# any early termination (no calls to return), to make sure that the
# database does not get written.

# TODO(tammo): Get rid of the 'ANY' and/or 'NONE' special values in
# Hwid.component_map.  Instead add not_present_components and
# (optionally) anything_goes_components lists.  If component classes
# are not in either the map or the not_present list, they are
# implicitly in anything_goes.

# TODO(tammo): Add examples to the command line function docstrings.

# TODO(tammo): Hwid should be Bom, and it should be two lists of
# component classes (missing and any) and a map of classes to
# canonical names (either an atom, or a list).  Device data should
# track variant information.  Variant data should also just be a list
# of Bom datastructures, but named with variant codes?  That way the
# full bom for each hwid can be calcualted by just merging the primary
# and variant bom data.


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


# TODO(tammo): Move CompDb and HardwareDb into their own files, and
# then pull relevant functions into them as methods.


class CompDb(YamlDatastore):

  def _BuildNameResultMap(self):
    self.name_result_map = dict(
      (comp_name, probe_result)
      for comp_class, comp_map in self.registry.items()
      for comp_name, probe_result in comp_map.items())

  def _BuildResultNameMap(self):
    self.result_name_map = dict(
      (probe_result, comp_name)
      for comp_class, comp_map in self.registry.items()
      for comp_name, probe_result in comp_map.items())

  def _BuildNameClassMap(self):
    self.name_class_map = dict(
      (comp_name, comp_class)
      for comp_class, comp_map in self.registry.items()
      for comp_name in comp_map)

  def _PreprocessData(self):
    self._BuildResultNameMap()
    self._BuildNameResultMap()
    self._BuildNameClassMap()
    # TODO(tammo): Enforce invariants here.

  def __init__(self, path):
    self._path = path
    full_path = os.path.join(path, COMPONENT_DB_FILENAME)
    if not os.path.isfile(full_path):
      raise InvalidDataError, ('ComponentDB not found (expected path is %r).' %
                               full_path)
    with open(full_path, 'r') as f:
      self.__dict__.update(ComponentRegistry.Decode(f.read()).__dict__)
    self._PreprocessData()

  def Write(self):
    """Write the component_db and all device data files."""
    # TODO(tammo): Enforce invariants here.
    data = ComponentRegistry(**dict(
        (field_name, getattr(self, field_name))
        for field_name in ComponentRegistry.FieldNames()))
    self.WriteOnDiff(COMPONENT_DB_FILENAME, data.Encode())


class Device(YamlDatastore):

  def _BuildReverseIcMap(self):
    self._reverse_ic_map = {}
    for index, data in self.initial_configs.items():
      for bom_name in data.enforced_for_boms:
        self._reverse_ic_map.setdefault(bom_name, set()).add(index)

  def _BuildHwidStatusMap(self):
    self._hwid_status_map = {}
    status_globs = [(pattern, status)
                    for status in LIFE_CYCLE_STAGES
                    for pattern in getattr(self.hwid_status, status)]
    for pattern, status in status_globs:
      match = HWID_GLOB_RE.findall(pattern)
      if not match:
        raise Error, 'illegal hwid_status pattern %r' % pattern
      bom, variant, volatile = match.pop()
      target_boms = [bom] if bom != '*' else self.boms.keys()
      target_vars = [variant] if variant != '*' else self.variants.keys()
      target_vols = [volatile] if volatile != '*' else self.volatiles.keys()
      for bom_name in target_boms:
        var_status = self._hwid_status_map.setdefault(bom_name, {})
        for var_code in target_vars:
          vol_status = var_status.setdefault(var_code, {})
          for vol_code in target_vols:
            prev_status = vol_status.get(vol_code, None)
            if prev_status is not None:
              raise Error, ('hwid_status pattern %r too broad, '
                            '%s %s-%s already has status %r' %
                            (pattern, bom_name, var_code,
                             vol_code, prev_status))
            vol_status[vol_code] = status

  def _PreprocessData(self):
    self._BuildReverseIcMap()
    self._BuildHwidStatusMap()
    # TODO(tammo): Enforce invariants here.

  def CommonInitialConfigs(self, target_bom_names):
    """Return all initial_config indices shared by the target boms."""
    return set().union(*[self._reverse_ic_map.get(bom_name, set())
                         for bom_name in target_bom_names])

  def CommonMissingClasses(self, target_bom_names):
    boms = [self.boms[bom_name] for bom_name in target_bom_names]
    return set().union(*[set(bom.primary.classes_missing) for bom in boms])

  def CommonDontcareClasses(self, target_bom_names):
    boms = [self.boms[bom_name] for bom_name in target_bom_names]
    return set().union(*[set(bom.primary.classes_dontcare) for bom in boms])

  def GetVolatileCodes(self, bom_name, variant_code, status_mask):
    variant_status_map = self._hwid_status_map.get(bom_name, {})
    volatile_status_map = variant_status_map.get(variant_code, {})
    return set(volatile_code for volatile_code, status
               in volatile_status_map.items()
               if status not in status_mask)

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
      raise Error('too few available bom names (only %d left)' %
                  len(available_names))
    return available_names[:count]

  def FmtHwid(self, bom, variant, volatile):
    """Generate HWID string.  See the hwid spec for details."""
    text = '%s %s %s-%s' % (self.board_name, bom, variant, volatile)
    assert text.isupper(), 'HWID cannot have lower case text parts.'
    return str(text + ' ' + HwidChecksum(text))

  def __init__(self, path, board_name):
    self._path = path
    full_path = os.path.join(path, board_name)
    if not os.path.isfile(full_path):
      raise Error, 'path %r is not a board file'
    with open(full_path, 'r') as f:
      self.__dict__.update(DeviceData.Decode(f.read()).__dict__)
    self.board_name = board_name
    self._PreprocessData()

  def Write(self):
    # TODO(tammo): Enforce invariants here.
    data = DeviceData(**dict((field_name, getattr(self, field_name))
                             for field_name in DeviceData.FieldNames()))
    self.WriteOnDiff(self.board_name, data.Encode())


class HardwareDb(object):

  def __init__(self, path):
    """Read the component_db and all device data files."""
    self.comp_db = CompDb(path)
    self.devices = dict((entry, Device(path, entry))
                        for entry in os.listdir(path)
                        if entry.isalpha() and entry.isupper())

  def Write(self):
    """Write the component_db and all device data files."""
    self.comp_db.Write()
    for device in self.devices.values():
      device.Write()


class XCompDb(YamlDatastore):

  def __init__(self, path):
    self._path = path
    full_path = os.path.join(path, COMPONENT_DB_FILENAME)
    if not os.path.isfile(full_path):
      raise InvalidDataError, (
          'ComponentDB not found (expected path is %r).' % full_path)
    with open(full_path, 'r') as f:
      self.__dict__.update(XCompData.Decode(f.read()).__dict__)

  def Convert(self):
    data = ComponentRegistry(
      components=self.registry,
      status=StatusData(**dict((status, self.status_map.get(status, []))
                               for status in LIFE_CYCLE_STAGES)))
    self.WriteOnDiff(COMPONENT_DB_FILENAME, data.Encode())


class XHardwareDb(YamlDatastore):

  def __init__(self, path):
    """Read the component_db and all device data files."""
    self._path = path
    self.comp_db = XCompDb(path)
    device_paths = [(entry, os.path.join(path, entry))
                    for entry in os.listdir(path)
                    if entry.isalpha() and entry.isupper()]
    device_paths = [(e, p) for (e, p) in device_paths if os.path.isfile(p)]
    self.devices = dict((e, XDevice.Decode(open(p, 'r').read()))
                        for e, p in device_paths)

  def Convert(self):
    def ConvertBom(xhwid):
      primary = ComponentData(
        components={},
        classes_dontcare=[],
        classes_missing=[])
      for comp_class, comp_name in xhwid.component_map.items():
        if comp_name == 'ANY':
          primary.classes_dontcare.append(comp_class)
        elif comp_name == 'NONE':
          primary.classes_missing.append(comp_class)
        else:
          primary.components[comp_class] = comp_name
      data = BomData(
        primary=primary,
        variants=xhwid.variant_list)
      return data
    def ConvertVariant(comp_list):
      assert(len(comp_list) <= 1)
      data = ComponentData(
        components={},
        classes_dontcare=[],
        classes_missing=[])
      if len(comp_list) == 1:
        data.components['keyboard'] = comp_list.pop()
      return data
    def ConvertIc(ic, use_list):
      return InitialConfigData(
        constraints=ic,
        enforced_for_boms=use_list if use_list is not None else [])
    self.comp_db.Convert()
    for device_name, xdevice in self.devices.items():
      boms = dict((b_name, ConvertBom(b)) for b_name, b
                  in xdevice.hwid_map.items())
      variants = dict((v_name, ConvertVariant(v)) for v_name, v
                      in xdevice.variant_map.items())
      ics = dict((ic_name, ConvertIc(
            ic, xdevice.initial_config_use_map.get(
              ic_name, None)))
                 for ic_name, ic in xdevice.initial_config_map.items())
      status = StatusData(**dict(
          (status, xdevice.hwid_status_map.get(status, []))
          for status in LIFE_CYCLE_STAGES))
      device = DeviceData(
        vpd_ro_fields=xdevice.vpd_ro_field_list,
        volatiles=xdevice.volatile_map,
        volatile_values=xdevice.volatile_value_map,
        hwid_status=status,
        initial_configs=ics,
        boms=boms,
        variants=variants)
      self.WriteOnDiff(device_name, device.Encode())


def CalcReverseComponentMap(bom_map):
  """Return dict of (comp_class: dict of (component: bom name set)) mappings.

  For each component in each comp_class, reveals the set of boms
  containing that component.
  """
  comp_class_map = {}
  for bom_name, bom in bom_map.items():
    for comp_class, comp_data in bom.primary.components.items():
      comp_map = comp_class_map.setdefault(comp_class, {})
      comps = comp_data if isinstance(comp_data, list) else [comp_data]
      for comp in comps:
        comp_bom_set = comp_map.setdefault(comp, set())
        comp_bom_set.add(bom_name)
  return comp_class_map


def CalcBiggestBomSet(rev_comp_map):
  """For the component with the most boms using it, return that bom set.

  If there multiple components have equal numbers of boms, only one
  will be returned.  Fails when no componets have any boms (KeyError).
  """
  return sorted([(len(bom_set), bom_set)
                 for comp_map in rev_comp_map.values()
                 for bom_set in comp_map.values()]).pop()[1]


def CalcFullBomSet(rev_comp_map):
  """Return the superset of all bom sets from the rev_comp_map."""
  return set(bom for comp_map in rev_comp_map.values()
             for bom_set in comp_map.values() for bom in bom_set)


def CalcCommonComponentMap(rev_comp_map):
  """Return (comp_class: comp) dict for only components with maximal bom set."""
  full_bom_set = CalcFullBomSet(rev_comp_map)
  return dict(
      (comp_class, comp)
      for comp_class, comp_map in rev_comp_map.items()
      for comp, comp_bom_set in comp_map.items()
      if comp_bom_set == full_bom_set)


def SplitReverseComponentMap(rev_comp_map):
  """Parition rev_comp_map into left and right parts by largest bom set.

  Calculate the set of common components shared by all of the bom in
  the rev_comp_map.  For the remaining components, use the largest set
  of boms that share one component as a radix and partition the
  remaining rev_comp_map data into left (data for boms in the largest
  bom set) and right (all other data).

  Returns:
    Obj containing the left and right rev_comp_map partitions, a dict
    of common components, and the bom superset for the input
    rev_comp_map (meaning the bom set matching the common components).
  """
  if not rev_comp_map:
    return None
  full_bom_set = CalcFullBomSet(rev_comp_map)
  split_bom_set = CalcBiggestBomSet(rev_comp_map)
  common_comp_map = {}
  left_rev_comp_map = {}
  right_rev_comp_map = {}
  for comp_class, comp_map in rev_comp_map.items():
    for comp, bom_set in comp_map.items():
      if bom_set == full_bom_set:
        common_comp_map[comp_class] = comp
      else:
        overlap_bom_set = bom_set & split_bom_set
        if overlap_bom_set:
          left_rev_comp_map.setdefault(comp_class, {})[comp] = overlap_bom_set
        extra_bom_set = bom_set - split_bom_set
        if extra_bom_set:
          right_rev_comp_map.setdefault(comp_class, {})[comp] = extra_bom_set
  return Obj(target_bom_set=full_bom_set,
             common_comp_map=common_comp_map,
             left_rev_comp_map=left_rev_comp_map,
             right_rev_comp_map=right_rev_comp_map)


def TraverseCompMapHierarchy(rev_comp_map, branch_cb, leaf_cb, cb_arg):
  """Derive component-usage hwid hierarchy and eval callback at key points.

  The component data in rev_comp_map is used to derive a tree
  structure where branch nodes indicate a set of components that are
  shared by all of the boms across the branches subtrees.  Callback
  functions are evaluated both for each branch and also for each leaf
  node.

  Args:
    rev_comp_map: A reverse component map.
    branch_cb: Callback funtion to be executed at branch nodes
      (indicating the existence of common components).
    leaf_cb: Callback function to be executed at lead nodes (meaning
      specific boms).
    cb_arg: Argument passed to both callbacks.  Branch callbacks must
      return updated versions of this data, which will be passsed to
      the recursive traversal of contained subtrees.
  Returns:
    Nothing.
  """
  def SubTraverse(rev_comp_map, cb_arg, depth):
    """Recursive helper; tracks recursion depth and allows cb_arg update."""
    split = SplitReverseComponentMap(rev_comp_map)
    if split is None:
      return
    if split.common_comp_map:
      cb_arg = branch_cb(depth, cb_arg, split.target_bom_set,
                         split.common_comp_map)
      depth += 1
    SubTraverse(split.left_rev_comp_map, cb_arg, depth)
    if not split.left_rev_comp_map:
      leaf_cb(depth, cb_arg, split.target_bom_set)
    SubTraverse(split.right_rev_comp_map, cb_arg, depth)
  SubTraverse(rev_comp_map, cb_arg, 0)


def PrintHwidHierarchy(device, bom_map, status_mask):
  """Hierarchically show all details for all specified BOMs.

  Details include both primary and variant component configurations,
  initial config, and status.
  """
  def ShowCommon(depth, masks, bom_name_set, common_comp_map):
    common_output = {}
    common_ic = device.CommonInitialConfigs(bom_name_set) - masks.ic
    if common_ic:
      common_output['initial_config'] = ', '.join([str(x) for x in common_ic])
    common_missing = device.CommonMissingClasses(bom_name_set) - masks.missing
    if common_missing:
      common_output['classes missing'] = ', '.join(common_missing)
    common_wild = device.CommonDontcareClasses(bom_name_set) - masks.wild
    if common_wild:
      common_output['classes dontcare'] = ', '.join(common_wild)
    print (depth * '  ') + '-'.join(sorted(bom_name_set))
    for line in FmtLeftAlignedDict(common_output):
      print (depth * '  ') + '  ' + line
    for line in FmtRightAlignedDict(common_comp_map):
      print (depth * '  ') + '  (primary) ' + line
    print ''
    return Obj(ic=masks.ic | common_ic,
               missing=masks.missing | common_missing,
               wild=masks.wild | common_wild)
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
  def ShowBom(depth, masks, bom_name_set):
    for bom_name in sorted(bom_name_set):
      common_ic = device.CommonInitialConfigs(set([bom_name])) - masks.ic
      if common_ic:
        print (depth * '  ') + (
          'initial_config: %s' % ', '.join([str(x) for x in common_ic]))
        print ''
        depth += 2
      ShowHwids(depth, bom_name)
  masks = Obj(ic=set(), missing=set(), wild=set())
  TraverseCompMapHierarchy(CalcReverseComponentMap(bom_map),
                           ShowCommon, ShowBom, masks)


def ProcessComponentCrossproduct(data, board, comp_list):
  """Return new combinations for board using the components from comp_list.

  The components in the comp_list are supplemented with those for any
  missing component classes if a common component can be found for
  that component class for the specified board.  The result is the
  collection of component configurations that are not already
  registered for the board, generated using the components in
  comp_list.  For example, if comp_list contains 2 components of one
  comp_class and 3 components of another, and if all of these are new
  to the board, this routine will produce 2 * 3 = 6 new component
  configurations.
  """
  def ClassifyInputComponents(comp_list):
    """Return dict of (comp_class: comp list), associating comps to classes."""
    comp_db_class_map = data.comp_db.name_class_map
    comp_class_subset = set(comp_db_class_map[comp] for comp in comp_list)
    return dict((comp_class, [comp for comp in comp_list
                              if comp_db_class_map[comp] == comp_class])
                for comp_class in comp_class_subset)
  def DoCrossproduct(available_comp_data_list, target_comp_map_list):
    """Return list of comp maps corresonding to all possible combinations.

    Remove (comp_class, comp_list) pairs from the available list and
    combine each of these components recursively with those left of
    the available list.  Result is a list of (comp_class: comp) dicts.
    """
    if not available_comp_data_list:
      return [dict(target_comp_map_list)]
    (comp_class, comp_list) = available_comp_data_list[0]
    result = []
    for comp in comp_list:
      new_target_comp_map_list = target_comp_map_list + [(comp_class, comp)]
      result += DoCrossproduct(available_comp_data_list[1:],
                               new_target_comp_map_list)
    return result
  comp_map = ClassifyInputComponents(comp_list)
  hwid_map = data.devices[board].hwid_map
  rev_comp_map = CalcReverseComponentMap(hwid_map)
  common_comp_map = CalcCommonComponentMap(rev_comp_map)
  class_coverage = set(comp_map) | set(common_comp_map)
  if class_coverage != set(rev_comp_map):
    raise Error('need component data for: %s' % ', '.join(
        set(rev_comp_map) - class_coverage))
  existing_comp_map_str_set = set(ComponentConfigStr(hwid.component_map)
                                  for hwid in hwid_map.values())
  new_comp_map_list = DoCrossproduct(comp_map.items(), common_comp_map.items())
  return [comp_map for comp_map in new_comp_map_list
          if ComponentConfigStr(comp_map) not in existing_comp_map_str_set]


def CookProbeResults(data, probe_results, board_name):
  """Correlate probe results with component and board data.

  For components, return a comp_class:comp_name dict for matches.  For
  volatile and initial_config, return corresponding sets of index
  values where the index values correspond to existing board data that
  matches the probe results.
  """
  def CompareMaps(caption, map1, map2):
    if all(map2.get(c, None) == v for c, v in map1.items()):
      return True
    # Try to provide more debug information
    logging.debug('Unmatchd set: %s', caption)
    logging.debug('---')
    for c, v1 in map2.items():
      v2 = map2.get(c, None)
      logging.debug('%s: Expected="%s", Probed="%s" (%s)', c, v1, v2,
                    'matched' if (v1 == v2) else 'UNMATCHED')
    logging.debug('---')

  results = Obj(
      matched_components={},
      matched_volatiles=[],
      matched_volatile_tags=[],
      matched_initial_config_tags=[])
  results.__dict__.update(probe_results.__dict__)
  comp_reference_map = data.comp_db.result_name_map
  for probe_class, probe_value in probe_results.found_components.items():
    if probe_value in comp_reference_map:
      results.matched_components[probe_class] = comp_reference_map[probe_value]
  device = data.devices[board_name]
  volatile_reference_map = dict(
      (v, c) for c, v in device.volatile_value_map.items())
  results.matched_volatiles = dict(
      (c, volatile_reference_map[v])
      for c, v in probe_results.volatiles.items()
      if v in volatile_reference_map)
  for volatile_tag, volatile_map in device.volatile_map.items():
    if (CompareMaps(volatile_tag, volatile_map, results.matched_volatiles)
        and volatile_tag not in results.matched_volatile_tags):
        results.matched_volatile_tags.append(volatile_tag)
  for initial_config_tag, ic_map in device.initial_config_map.items():
    if (CompareMaps(initial_config_tag, ic_map, probe_results.initial_configs)
        and initial_config_tag not in results.matched_initial_config_tags):
      results.matched_initial_config_tags.append(initial_config_tag)
  return results


def MatchHwids(data, cooked_results, board_name, status_set):
  """Return a list of all HWIDs compatible with the cooked probe results."""
  logging.info('looking for HWIDs to match:\n%s', YamlWrite(cooked_results))
  logging.info('matching only status: %s', ', '.join(status_set))
  device = data.devices[board_name]
  matching_hwids = []
  for bom_name, bom_details in device.hwid_map.items():
    match = True
    # TODO(tammo): The expected component_map used here should include
    # variant component data, ie the outer loop should be over
    # variants and not boms.
    for comp_class, expected_name in bom_details.component_map.items():
      if expected_name == 'ANY':
        continue
      found_name = cooked_results.matched_components.get(comp_class, None)
      if expected_name == found_name:
        continue
      match = False
      break
    if not match:
      continue
    logging.info('considering bom %s', bom_name)
    found_component_names = cooked_results.matched_components.values()
    for variant_code in bom_details.variant_list:
      variant_details = device.variant_map[variant_code]
      logging.info('variant details: %r, found_component_names: %r',
                   variant_details, found_component_names)
      if not all(comp_name in found_component_names
                 for comp_name in variant_details):
        continue
      logging.info('variant %r matched, checking volatiles', variant_code)
      for volatile_code in cooked_results.matched_volatile_tags:
        status = device.GetHwidStatus(bom_name, volatile_code, variant_code)
        logging.info('volatile_code %r has status %r', volatile_code, status)
        if status in status_set:
          hwid = device.FmtHwid(bom_name, volatile_code, variant_code)
          matching_hwids.append(hwid)
  return matching_hwids


def LookupHwidProperties(data, hwid):
  """TODO(tammo): Add more here XXX."""
  props = ParseHwid(hwid)
  if props.board not in data.devices:
    raise Error, 'hwid %r board %s could not be found' % (hwid, props.board)
  device = data.devices[props.board]
  if props.bom not in device.hwid_map:
    raise Error, 'hwid %r bom %s could not be found' % (hwid, props.bom)
  hwid_details = device.hwid_map[props.bom]
  if props.variant not in hwid_details.variant_list:
    raise Error, ('hwid %r variant %s does not match database' %
                  (hwid, props.variant))
  if props.volatile not in device.volatile_map:
    raise Error, ('hwid %r volatile %s does not match database' %
                  (hwid, props.volatile))
  props.status = device.GetHwidStatus(props.bom, props.volatile, props.variant)
  # TODO(tammo): Refactor if FilterExternalHwidAttrs is pre-computed.
  initial_config_set = CommonInitialConfig(device, set([props.bom]))
  props.initial_config = next(iter(initial_config_set), None)
  props.vpd_ro_field_list = device.vpd_ro_field_list
  props.component_map = hwid_details.component_map
  return props


@Command('create_hwids',
         CmdArg('-b', '--board', required=True),
         CmdArg('-c', '--comps', nargs='*', required=True),
         CmdArg('-x', '--make_it_so', action='store_true'),
         CmdArg('-v', '--variants', nargs='*'))
def CreateHwidsCommand(config, data):
  """Derive new HWIDs from the cross-product of specified components.

  For the specific board, the specified components indicate a
  potential set of new HWIDs.  It is only necessary to specify
  components that are different from those commonly shared by the
  boards existing HWIDs.  The target set of new HWIDs is then derived
  by looking at the maxmimal number of combinations between the new
  differing components.

  By default this command just prints the set of HWIDs that would be
  added.  To actually create them, it is necessary to specify the
  make_it_so option.
  """
  # TODO(tammo): Validate inputs -- comp names, variant names, etc.
  comp_map_list = ProcessComponentCrossproduct(data, config.board, config.comps)
  bom_count = len(comp_map_list)
  bom_name_list = data.devices[config.board].AvailableBomNames(bom_count)
  variant_list = config.variants if config.variants else []
  hwid_map = dict((bom_name, Hwid(component_map=comp_map,
                                  variant_list=variant_list))
                  for bom_name, comp_map in zip(bom_name_list, comp_map_list))
  device = data.devices[config.board]
  device.hwid_status_map.setdefault('proposed', []).extend(bom_name_list)
  PrintHwidHierarchy(device, hwid_map, set([None]))
  if config.make_it_so:
    #TODO(tammo): Actually add to the device hwid_map, and qualify.
    pass


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
  for board, device in hw_db.devices.items():
    if config.board:
      if not config.board == board:
        continue
    else:
      print '---- %s ----\n' % board
    status_mask = config.status if config.status else set([None])
    PrintHwidHierarchy(device, device.boms, status_mask)


@Command('list_hwids',
         CmdArg('-b', '--board'),
         CmdArg('-s', '--status', default='supported'),
         CmdArg('-v', '--verbose', action='store_true'))
def ListHwidsCommand(config, data):
  """Print sorted list of supported HWIDs.

  Optionally list HWIDs for other status values, or '' for all HWIDs.
  Optionally show the status of each HWID.  Optionally limit the list
  to a specific board.
  """
  result_list = []
  for board, device in data.devices.items():
    if config.board:
      if not config.board == board:
        continue
    for bom, hwid in device.hwid_map.items():
      for volind in device.volatile_map:
        for variant in hwid.variant_list:
          status = device.GetHwidStatus(bom, volind, variant)
          if (config.status != '' and
              (status is None or config.status != status)):
            continue
          result = device.FmtHwid(bom, volind, variant)
          if config.verbose:
            result = '%s: %s' % (status, result)
          result_list.append(result)
  for result in sorted(result_list):
    print result


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
    rev_comp_map = CalcReverseComponentMap(device.boms)
    common_comp_map = CalcCommonComponentMap(rev_comp_map)
    print 'common:'
    for line in FmtRightAlignedDict(common_comp_map):
      print '  ' + line
    remaining_comp_class_set = set(rev_comp_map) - set(common_comp_map)
    sorted_remaining_comp_class_list = sorted(
        [(len(rev_comp_map[comp_class]), comp_class)
         for comp_class in  remaining_comp_class_set])
    while sorted_remaining_comp_class_list:
      comp_class = sorted_remaining_comp_class_list.pop()[1]
      comp_map = dict((comp, ', '.join(sorted(bom_set)))
                      for comp, bom_set in rev_comp_map[comp_class].items())
      print comp_class + ':'
      for line in FmtRightAlignedDict(comp_map):
        print '  ' + line


@Command('assimilate_probe_data',
         CmdArg('-b', '--board'),
         CmdArg('--bom'))
def AssimilateProbeData(config, data):
  """Merge new data from stdin into existing data, optionally create a new bom.

  By default only new component probe results are added to the
  component database.  Canonical names are automatically chosen for
  these new components, which can be changed later by renaming.

  If a board is specified, then any volatile or initial_config data is
  added to the corresponding board data.

  If a bom name is specified, and if a bom of that name does not
  already exist, attempt to create it, and associate those properties
  specified by the input data.  If there is already a bom with the
  same properties, the request will fail.  If such a bom already
  exists with the specified name, ensure that its initial_config and
  any initial_config info in the input data match.

  Variant data that cannot be derived from the input data must be
  added to the bom later using other commands.

  Boms created using this command do not have any status, and hence
  there is no binding made with any new volatile properties add using
  the input data.
  """
  probe_results = Obj(**YamlRead(sys.stdin.read()))
  # TODO(tammo): Refactor to use CookProbeResults.
  components = getattr(probe_results, 'found_components', {})
  registry = data.comp_db.registry
  if not set(components) <= set(registry):
    logging.critical('data contains component classes that are not preset in '
                     'the component_db, specifically %r',
                     sorted(set(components) - set(registry)))
  reverse_registry = data.comp_db.result_name_map
  component_match_dict = {}
  # TODO(tammo): Once variant data is properly mapped into the
  # component space, segregate any variant component data into a
  # variant list.
  for comp_class, probe_value in components.items():
    if probe_value in reverse_registry:
      component_match_dict[comp_class] = reverse_registry[probe_value]
      print 'found component %r for probe result %r' % (
          reverse_registry[probe_value], probe_value)
    else:
      comp_map = registry[comp_class]
      comp_name = '%s_%d' % (comp_class, len(comp_map))
      comp_map[comp_name] = probe_value
      component_match_dict[comp_class] = comp_name
      print 'adding component %r for probe result %r' % (comp_name, probe_value)
  if not config.board:
    if (hasattr(probe_results, 'volatile') or
        hasattr(probe_results, 'initial_config')):
      logging.warning('volatile and/or initial_config data is only '
                      'assimilated when a board is specified')
    return
  device = data.devices[config.board]
  for comp_class in getattr(probe_results, 'missing_components', {}):
    component_match_dict[comp_class] = 'NONE'
  component_match_dict_str = ComponentConfigStr(component_match_dict)
  bom_name_match = None
  for bom_name, bom in device.hwid_map.items():
    if ComponentConfigStr(bom.component_map) == component_match_dict_str:
      bom_name_match = bom_name
      print 'found bom match: %r' % bom_name
      break
  reverse_volatile_map = dict((v, c) for c, v in
                              device.volatile_value_map.items())
  probe_volatiles = getattr(probe_results, 'volatiles', {})
  volatile_match_dict = {}
  for volatile_class, probe_value in probe_volatiles.items():
    if probe_value in reverse_volatile_map:
      volatile_match_dict[volatile_class] = reverse_volatile_map[probe_value]
    else:
      volatile_name = '%s_%d' % (volatile_class, len(device.volatile_value_map))
      device.volatile_value_map[volatile_name] = probe_value
      volatile_match_dict[volatile_class] = volatile_name
  for volatile_index, volatile in device.volatile_map.items():
    if volatile_match_dict == volatile:
      volatile_match_index = volatile_index
      print 'found volatile match: %r' % volatile_match_index
      break
  else:
    volatile_match_index = AlphaIndex(len(device.volatile_map))
    device.volatile_map[volatile_match_index] = volatile_match_dict
    print 'added volatile: %r' % volatile_match_index
  probe_initial_config = getattr(probe_results, 'initial_configs', {})
  for initial_config_index, initial_config in device.initial_config_map.items():
    if probe_initial_config == initial_config:
      initial_config_match_index = initial_config_index
      print 'found initial_config match: %r' % initial_config_match_index
      break
  else:
    initial_config_match_index = str(len(device.initial_config_map))
    device.initial_config_map[initial_config_match_index] = probe_initial_config
    print 'added initial_config: %r' % initial_config_match_index
  if not config.bom:
    return
  # TODO(tammo): Validate input bom name string.
  if bom_name_match and bom_name_match != config.bom:
    print 'matching bom %r already exists, ignoring bom argument %r' % (
        bom_name_match, config.bom)
    return
  bom_name = config.bom
  if bom_name not in device.hwid_map:
    bom = Hwid.New()
    bom.component_map = component_match_dict
    device.hwid_map[config.bom] = bom
    print 'added bom: %r' % bom_name
  elif (ComponentConfigStr(device.hwid_map[bom_name].component_map) !=
        component_match_dict_str):
    print 'bom %r exists, but component list differs from this data' % bom_name
    # TODO(tammo): Print exact differences.
    return
  # TODO(tammo): Another elif to test that initial_config settings match.
  else:
    print 'bom %r exists and component list matches' % bom_name
  ic_use_list = device.initial_config_use_map.setdefault(
      initial_config_match_index, [])
  if bom_name not in ic_use_list:
    ic_use_list.append(bom_name)


@Command('board_create',
         CmdArg('board_name'))
def CreateBoard(config, data):
  """Create an fresh empty board with specified name."""
  if not config.board_name.isalpha():
    print 'ERROR: Board names must be alpha-only.'
    return
  board_name = config.board_name.upper()
  if board_name in data.devices:
    print 'ERROR: Board %s already exists.' % board_name
    return
  data.devices[board_name] = Device.New()


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


@Command('legacy_export',
         CmdArg('-b', '--board', required=True),
         CmdArg('-d', '--dest_dir', required=True),
         CmdArg('-e', '--extra'),
         CmdArg('-s', '--status', default='supported'))
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


@Command('rename_comps')
def RenameComponents(config, data):
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
  #XXX hw_db = XHardwareDb(config.data_path).Convert()
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
