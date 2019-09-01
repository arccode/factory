#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Converts a directory of v1 component files into one v2 HWID file.

Designed to be used to convert ALEX component files to v2.
"""
import argparse
import os
import yaml

from os import listdir
from os.path import isfile, join


class Hwid(object):
  """BOM object"""

  def __init__(self, name):
    self.name = name
    self.components = {}
    self.variants = []
    self.volatiles = []
    self.missing = []
    self.dontcare = []

  def GetV2BomDict(self):
    """Creates a BOM dictionary from the current BOM in the v2 format.

    Returns:
      Dictionary containing the data from the current BOM.
    """
    bom_dict = dict()
    primary = {'classes_dontcare': sorted(self.dontcare),
               'classes_missing': sorted(self.missing),
               'components': self.components}
    bom_dict = {'primary': primary, 'variants': sorted(self.variants)}
    return bom_dict


class InitialConfig(object):
  """Initial config"""

  def __init__(self, num):
    self.num = num
    self.constraints = {}
    self.enforced_boms = []

  def GetV2InitialConfigDict(self):
    """Creates an initial config dictionary from the current initial config in
    the v2 format.

    Returns:
      Dictionary containing the data from the current initial config.
    """
    config_dict = {'constraints': self.constraints,
                   'enforced_for_boms': sorted(self.enforced_boms)}
    return config_dict


class Variant(object):
  """HWID variant"""

  def __init__(self):
    self.letter = ''
    self.components = {}
    self.missing = []
    self.dontcare = []

  def Equals(self, var):
    """Checks if this variant is the same as another variant.

    Args:
      var: variant to which this variant is compared.

    Returns:
      False if the variants are different, and True otherwise.
    """
    return ((self.components == var.components) and
            (self.missing == var.missing))

  def GetV2VariantDict(self):
    """Creates an variant dictionary from the current variant in the v2 format.

    Returns:
      Dictionary containing the data from the current variant.
    """
    variant_dict = {'classes_dontcare': sorted(self.dontcare),
                    'classes_missing': sorted(self.missing),
                    'components': self.components}
    return variant_dict


class Volatile(object):
  """HWID volatile"""

  def __init__(self, name):
    self.name = name
    self.volatile_values = {}


def ConvertV1Dir(directory, outfile):
  """Creates a v2 HWID file using v1 files in directory and saving to outfile.

  Args:
    directory: Directory containing v1 component files.
    outfile: v2 file that is created with data from the v1 files.
  """
  all_files = [f for f in listdir(directory) if isfile(join(directory, f))]
  comp_files = []
  for f in all_files:
    # Check if the file is a v1 component file if so add it to comp_files
    if f[:16] == 'components_SAMS_':
      comp_files.append(f)
  comp_files = sorted(comp_files)
  hwids = {}
  for f in comp_files:
    component_file = open(os.path.join(directory, f), 'r')
    # Removes 'components' from the front of the board name because that is the
    # format used for omaha queries
    board_name = f[11:-5]
    # The portion following the '-' is to descern for which language the
    # component file is meant, and if the component file is a variant. Remove
    # this portion and check later if the current component file is a variant of
    # an existing BOM by comparing the HWID
    hwid = Hwid(board_name)
    # Add components to BOM object
    for line in component_file:
      # Get all components for the BOM
      if (line[5:13] == 'part_id_' or
          line[5:15] == 'vendor_id_'):
        part = ''
        if line[5:13] == 'part_id_':
          temp = line[13:]
          templist = temp.partition(':')
          part = templist[0][:-1]
        elif line[5:15] == 'vendor_id_':
          temp = line[15:]
          templist = temp.partition(':')
          part = templist[0][:-1]
        # Remove components that shouldn't be included
        # Add more fields in the same manner if they need to be removed as well
        if part == 'hwqual':
          continue
        temp = templist[2][1:]
        partlist = temp.rpartition(',')
        # 'Not Present' and '*' mean that the component is missing for the
        # current variat and as such, are not added to the varaint's list of
        # components
        if (partlist[0][2:-2] == 'Not Present' or
            partlist[0][2:-2] == '*'):
          continue
        part_name = ''
        # Check if the actual name of the component is listed, and if so, uses
        # the actual name for the component
        if '#' in partlist[2]:
          part_name = partlist[2].partition('#')[2][1:]
        else:
          part_name = partlist[0][2:-2]
        # Normalize the components name for style uniformity
        part_name = part_name.replace(' ', '_')
        part_name = part_name.replace('\n', '')
        part_name = part_name.lower()
        hwid.components[part] = part_name
    # If the HWID is not already added, adds it, otherwise, it creates a new
    # variant for the HWID
    if not hwid.name in hwids:
      hwids[hwid.name] = hwid
    else:
      old_hwid = hwids[hwid.name]
      # Checks if there are existing variants. If not, two variants are made
      # with the differences between the two HWIDs. If there are existing
      # variants, a check is made if there is already a similar variant existing
      # and if not, a new variant is added to the exising ones. Only fields that
      # are common to all variants are included in the primary section of the
      # BOM.
      if len(old_hwid.variants) == 0:
        var1 = Variant()
        var2 = Variant()
        for old_key, old_value in sorted((k, v) for k, v in
                                         old_hwid.components.items()):
          for new_key, new_value in sorted((k, v) for k, v in
                                           hwid.components.items()):
            if not old_key in hwid.components:
              var1.components[old_key] = old_value
              var2.missing.append(old_key)
            if not new_key in old_hwid.components:
              var1.missing.append(new_key)
              var2.components[new_key] = new_value
            if old_key == new_key and not old_value == new_value:
              var1.components[old_key] = old_value
              var2.components[new_key] = new_value
        for k in sorted(k for k in var1.components.keys()):
          if k in old_hwid.components:
            del old_hwid.components[k]
        for k in sorted(k for k in var2.components.keys()):
          if k in old_hwid.components:
            del old_hwid.components[k]
        old_hwid.variants.append(var1)
        old_hwid.variants.append(var2)
        del hwids[old_hwid.name]
        hwids[old_hwid.name] = old_hwid
      else:
        new_variant = Variant()
        for old_key, old_value in sorted((k, v) for k, v in
                                         old_hwid.components.items()):
          for new_key, new_value in sorted((k, v) for k, v in
                                           hwid.components.items()):
            if not old_key in hwid.components:
              for var in old_hwid.variants:
                var.components[old_key] = old_value
              new_variant.missing.append(old_key)
            if not new_key in old_hwid.components:
              for var in old_hwid.variants:
                if not new_key in var.components:
                  var.missing.append(new_key)
              new_variant.components[new_key] = new_value
            if old_key == new_key and not old_value == new_value:
              for var in old_hwid.variants:
                var.components[old_key] = old_value
              new_variant.components[new_key] = new_value
        for var in old_hwid.variants:
          for k in sorted(k for k in var.components.keys()):
            if (not k in new_variant.components and
                not k in new_variant.missing):
              new_variant.missing.append(k)
        old_hwid.variants.append(new_variant)
        for var in old_hwid.variants:
          for k in sorted(k for k in var.components.keys()):
            if k in old_hwid.components:
              del old_hwid.components[k]
        del hwids[old_hwid.name]
        hwids[old_hwid.name] = old_hwid
    component_file.close()
  MakeV2FileFromV1(hwids, outfile)


def MakeV2FileFromV1(hwids, outfile):
  """Creates a v2 file from the list of hwids and saves it to outfile.

  Args:
    hwids: List of BOM objects.
    outfile: v2 file that is created with data from the v1 files.
  """
  variants = []
  all_components = []
  # Create a list of all possible component classes
  for name, hwid in sorted((k, v) for k, v in hwids.items()):
    for comp in sorted(k for k in hwid.components.keys()):
      if not comp in all_components:
        all_components.append(comp)
    for var in hwid.variants:
      for comp in sorted(k for k in var.components.keys()):
        if not comp in all_components:
          all_components.append(comp)
      for miss in var.missing:
        if not miss in all_components:
          all_components.append(miss)
  v2_file = open(outfile, 'w')
  v2_file.write('# WARNING: This file is AUTOMATICALLY GENERATED, do not edit.'
                + '\n')
  v2_file.write('# The proper way to modify this file is using the hwid_tool.'
                + '\n')
  v2_file.write('boms:\n')
  for name, hwid in sorted((k, v) for k, v in hwids.items()):
    v2_file.write(('\t' + name + ':\n\t\tprimary:\n\t\t\tclasses_dontcare: []'
                   + '\n\t\t\tclasses_missing:').expandtabs(2))
    missing = []
    hwid_var_comps = set()
    hwid_var_miss = set()
    for var in hwid.variants:
      hwid_var_comps.update(comp for comp in var.components.keys())
      hwid_var_miss.update(miss for miss in var.missing)
    # Adds a component class to the missing section for the current BOM if the
    # class is not present in the BOM's primary components or any of its
    # variants.
    for comp in all_components:
      if (not comp in hwid.components) and (not comp in hwid_var_comps) and (
          not comp in hwid_var_miss):
        missing.append(comp)
    if len(missing) > 0:
      v2_file.write('\n')
      for miss in missing:
        v2_file.write(('\t\t\t- ' + str(miss) + '\n').expandtabs(2))
    else:
      v2_file.write(' []\n')
    v2_file.write(('\t\t\tcomponents:\n').expandtabs(2))
    for k, v in sorted((k, v) for k, v in hwid.components.items()):
      v2_file.write(('\t\t\t\t' + k + ': ' + v + '\n').expandtabs(2))
    v2_file.write(('\t\tvariants:\n').expandtabs(2))
    for var in sorted(GenerateVariantLetterList(hwid, variants)):
      v2_file.write(('\t\t- ' + var + '\n').expandtabs(2))
  v2_file.write(('hwid_status:\n\tdeprecated:\n').expandtabs(2))
  for name, hwid in sorted((k, v) for k, v in hwids.items()):
    v2_file.write(('\t- ' + name + ' AA-*\n').expandtabs(2))
  v2_file.write(('\teol: []\n\tqualified: []\n\tsupported: []\n').expandtabs(2))
  v2_file.write('initial_configs: {}\nvariants:\n')
  # For boms with no variants, an "empty" variant is added
  v2_file.write(('\tAA:\n\t\tclasses_dontcare: []\n\t\tclasses_missing: []\n')
                .expandtabs(2))
  v2_file.write(('\t\tcomponents: {}\n').expandtabs(2))
  # Add and number all of the variants for this HWID file
  for var in variants:
    var_num = variants.index(var)
    if var_num < 25:
      var_ltr = 'A' + chr(var_num + ord('A') + 1)
    else:
      var_num -= 26
      var_ltr = 'B' + chr(var_num + ord('A') + 1)
    v2_file.write(('\t' + var_ltr +
                   ':\n\t\tclasses_dontcare: []\n\t\tclasses_missing:')
                  .expandtabs(2))
    if len(var.missing) == 0:
      v2_file.write(' []\n')
    else:
      v2_file.write('\n')
    for miss in var.missing:
      v2_file.write(('\t\t- ' + miss + '\n').expandtabs(2))
    v2_file.write(('\t\tcomponents:').expandtabs(2))
    if len(var.components) == 0:
      v2_file.write(' {}\n')
    else:
      v2_file.write('\n')
    for k, v in sorted((k, v) for k, v in var.components.items()):
      v2_file.write(('\t\t\t' + k + ': ' + v + '\n').expandtabs(2))
  v2_file.write('volatile_values: {}\nvolatiles: {}\nvpd_ro_fields: []')
  v2_file.close()


def GenerateVariantLetterList(hwid, variants):
  """Returns a list of variant letters.

  Args:
    hwid: BOM object.
    variants: All current variants for the component file.

  Returns:
    List of variant letters.
  """
  var_letter_list = []
  if len(hwid.variants) == 0:
    var_letter_list.append('AA')
  for var_a in hwid.variants:
    already_exists = False
    for var_b in variants:
      if var_a.Equals(var_b):
        var_num = variants.index(var_b)
        if var_num < 25:
          var_letter_list.append('A' + chr(var_num + ord('A') + 1))
        else:
          var_num -= 26
          var_letter_list.append('B' + chr(var_num + ord('A') + 1))
        already_exists = True
    if not already_exists:
      variants.append(var_a)
      var_num = variants.index(var_a)
      if var_num < 25:
        var_letter_list.append('A' + chr(var_num + ord('A') + 1))
      else:
        var_num -= 26
        var_letter_list.append('B' + chr(var_num + ord('A') + 1))
  return var_letter_list


def ConvertV15(infile, outfile):
  """Converts a v1.5 file to v2.

  Args:
    infile: Input file.
    outfile: Output file.
  """
  v15_file = open(infile, 'r')
  v15_yaml = yaml.load(v15_file)
  v15_file.close()

  SaveYamlToV2File(ConvertV15YamlToV2Yaml(v15_yaml), outfile)


def ConvertV15YamlToV2Yaml(v15_yaml):
  """Converts a v15 yaml to a v2 yaml.

  Args:
    v15_yaml: v1.5 yaml dict.

  Returns:
    A v2 yaml dict.
  """
  boms = dict()
  for hwid in v15_yaml['hwid_map']:
    bom = Hwid(hwid)
    for cls, comp in v15_yaml['hwid_map'][hwid]['component_map'].items():
      if comp == 'NONE':
        bom.missing.append(cls)
      elif comp == 'ANY':
        bom.dontcare.append(cls)
      else:
        bom.components[cls] = comp
    bom.variants = v15_yaml['hwid_map'][hwid]['variant_list']
    boms[hwid] = bom
  hwid_status = dict()
  statuses = ['deprecated', 'eol', 'qualified', 'supported']
  for status in statuses:
    hwid_status[status] = list()
    if status in v15_yaml['hwid_status_map'].keys():
      for hwid in v15_yaml['hwid_status_map'][status]:
        hwid_split = hwid.rpartition('-')
        hwid_status[status].append('{0} *-{1}'.format(hwid_split[0],
                                                      hwid_split[2]))
  initial_configs = dict()
  for conf in v15_yaml['initial_config_map']:
    config = InitialConfig('{0}'.format(conf))
    config.constraints = v15_yaml['initial_config_map'][conf]
    initial_configs[conf] = config
  for conf in v15_yaml['initial_config_use_map']:
    if conf in initial_configs:
      initial_configs[conf].enforced_boms = (
          v15_yaml['initial_config_use_map'][conf])
  variants = dict()
  for var in v15_yaml['variant_map']:
    new_var = Variant()
    new_var.letter = var
    if v15_yaml['variant_map'][var]:
      new_var.components['keyboard'] = v15_yaml['variant_map'][var][0]
      if len(v15_yaml['variant_map'][var]) > 1:
        if not v15_yaml['variant_map'][var][1] == 'none':
          new_var.components['custom'] = v15_yaml['variant_map'][var][1]
        else:
          new_var.missing.append('custom')
    variants[var] = new_var
  volatiles = dict()
  for vol in v15_yaml['volatile_map']:
    new_vol = Volatile(vol)
    new_vol.volatile_values = v15_yaml['volatile_map'][vol]
    volatiles[vol] = new_vol
  volatile_values = {'hash_gbb': dict(),
                     'key_recovery': dict(),
                     'key_root': dict(),
                     'ro_ec_firmware': dict(),
                     'ro_main_firmware': dict()}
  for name, value in v15_yaml['volatile_value_map'].items():
    new_name = ''
    vol_type = value[:2]  # Type determines the format of the value in v2
    if vol_type == 'gv':
      new_name = 'hash_gbb_{0}'.format(len(volatile_values['hash_gbb']))
      new_value = value
      volatile_values['hash_gbb'][new_name] = new_value
    elif vol_type == 'kv':
      new_value = value
      if 'recovery' in name:
        new_name = 'key_recovery_{0}'.format(len(volatile_values[
            'key_recovery']))
        volatile_values['key_recovery'][new_name] = new_value
      elif 'root' in name:
        new_name = 'key_root_{0}'.format(len(volatile_values['key_root']))
        volatile_values['key_root'][new_name] = new_value
      else:
        raise AttributeError('Unknown key type. Found: {0}'.format(name))
    elif vol_type == 'ev':
      new_name = 'ro_ec_firmware_{0}'.format(len(volatile_values[
          'ro_ec_firmware']))
      new_value = '{0}#{1}'.format(value, name)
      volatile_values['ro_ec_firmware'][new_name] = new_value
    elif vol_type == 'mv':
      new_name = 'ro_main_firmware_{0}'.format(len(volatile_values[
          'ro_main_firmware']))
      new_value = '{0}#{1}'.format(
          value, name.replace('mpkeys/', '').replace('bios_', ''))
      volatile_values['ro_main_firmware'][new_name] = new_value
    else:
      raise AttributeError('Incorrect volatile type. Found: {0}'.format(
          vol_type))
    # Update the variable names for the volatile
    for vol in volatiles.values():
      for vol_key, vol_value in vol.volatile_values.items():
        if vol_value == name:
          vol.volatile_values[vol_key] = new_name
  vpd_ro_fields = v15_yaml['vpd_ro_field_list']

  boms_output, hwid_status_output, initial_configs_output, variants_output, \
      volatile_values_output, volatiles_output = (dict(), dict(), dict(),
                                                  dict(), dict(), dict())
  vpd_ro_fields_output = list()
  all_classes = set()
  for bom in boms.values():
    all_classes.update(bom.components.keys())
  for bom in boms.values():
    for cls in all_classes:
      if cls not in bom.components and cls not in bom.missing:
        bom.missing.append(cls)
    boms_output[bom.name] = bom.GetV2BomDict()
  hwid_status_output = hwid_status
  for conf in initial_configs.values():
    initial_configs_output[conf.num] = conf.GetV2InitialConfigDict()
  for var in variants.values():
    variants_output[var.letter] = var.GetV2VariantDict()
  for vol_type in volatile_values.values():
    for vol, value in vol_type.items():
      volatile_values_output[vol] = value
  for volatile in volatiles.values():
    volatiles_output[volatile.name] = volatile.volatile_values
  vpd_ro_fields_output = vpd_ro_fields

  # Add all of the dictionaries to the yaml_object
  yaml_output = {'boms': boms_output,
                 'hwid_status': hwid_status_output,
                 'initial_configs': initial_configs_output,
                 'variants': variants_output,
                 'volatile_values': volatile_values_output,
                 'volatiles': volatiles_output,
                 'vpd_ro_fields': vpd_ro_fields_output}

  return yaml_output


def SaveYamlToV2File(yaml_dict, outfile):
  """Saves a yaml dict to a v2 yaml file.

  Args:
    yaml_dict: dict that you want to save.
    outfile: output file.
  """
  v2_file = open(outfile, 'w')
  v2_file.write('# WARNING: This file is AUTOMATICALLY GENERATED, do not edit.'
                + '\n')
  v2_file.write('# The proper way to modify this file is using the hwid_tool.'
                + '\n')
  v2_file.write(yaml.dump(yaml_dict, indent=2, default_flow_style=False))
  v2_file.close()


def main():
  """Checks for command line arguments and calls the corresponding function"""
  parser = argparse.ArgumentParser(description='Convert from one HWID version'
                                   + ' to v2.')
  parser.add_argument('command', help='type of conversion to perform',
                      choices=['convert_v1_dir', 'convert_v15_file'])
  parser.add_argument('-d', '--directory', help='directory of old format')
  parser.add_argument('-i', '--infile', help='input file')
  parser.add_argument('-o', '--outfile', required=True, help='output file')
  args = parser.parse_args()
  if args.command == 'convert_v1_dir':
    ConvertV1Dir(args.directory, args.outfile)
  elif args.command == 'convert_v15_file':
    ConvertV15(args.infile, args.outfile)
  else:
    raise NotImplementedError('Function <' + args.command + '> does not exist')

if __name__ == '__main__':
  main()
