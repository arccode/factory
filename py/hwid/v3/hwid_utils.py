# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID v3 utility functions."""

import collections
import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import crosfw
from cros.factory.hwid.v3 import builder
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import decoder
from cros.factory.hwid.v3 import encoder
from cros.factory.hwid.v3 import rule
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import process_utils
from cros.factory.utils import json_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


def _HWIDMode(rma_mode):
  if rma_mode:
    return common.HWID.OPERATION_MODE.rma
  return common.HWID.OPERATION_MODE.normal


def BuildDatabase(database_path, probed_results, project, image_id,
                  add_default_comp=None, add_null_comp=None, del_comp=None,
                  region=None, chassis=None):
  db_builder = builder.DatabaseBuilder(project=project)
  db_builder.Update(probed_results, image_id, add_default_comp, add_null_comp,
                    del_comp, region, chassis)
  db_builder.Render(database_path)


def UpdateDatabase(database_path, probed_results, old_db, image_id=None,
                   add_default_comp=None, add_null_comp=None, del_comp=None,
                   region=None, chassis=None):
  db_builder = builder.DatabaseBuilder(db=old_db)
  db_builder.Update(probed_results, image_id, add_default_comp, add_null_comp,
                    del_comp, region, chassis)
  db_builder.Render(database_path)


def GenerateHWID(db, probed_results, device_info, vpd=None, rma_mode=False):
  """Generates a HWID v3 from the given data.

  The HWID is generated based on the given device info and probed results. If
  there are conflits of component information between device_info and
  probed_results, priority is given to device_info.

  Args:
    db: A Database object to be used.
    probed_results: A dict containing the probed results to be used.
    device_info: A dict of component infomation keys to their corresponding
        values. The format is device-specific and the meanings of each key and
        value vary from device to device. The valid keys and values should be
        specified in project-specific component database.
    vpd: None or a dict of RO and RW VPD values.  This argument should be set
        if some rules in the HWID database rely on the VPD values.
    rma_mode: Whether to verify components status in RMA mode.  Defaults to
        False.

  Returns:
    The generated HWID object.
  """
  hwid_mode = _HWIDMode(rma_mode)
  # Construct a base BOM from probe_results.
  device_bom = db.ProbeResultToBOM(probed_results)
  hwid = encoder.Encode(db, device_bom, mode=hwid_mode, skip_check=True)

  # Update unprobeable components with rules defined in db before verification.
  context_args = dict(hwid=hwid, device_info=device_info)
  if vpd is not None:
    context_args['vpd'] = vpd
  context = rule.Context(**context_args)
  db.rules.EvaluateRules(context, namespace='device_info.*')
  hwid.VerifyComponentStatus()
  return hwid


def DecodeHWID(db, encoded_string):
  """Decodes the given HWID v3 encoded string and returns the decoded info.

  Args:
    db: A Database object to be used.
    encoded_string: An encoded HWID string to test.

  Returns:
    The decoded HWIDv3 context object.
  """
  return decoder.Decode(db, encoded_string)


def ParseDecodedHWID(hwid):
  """Parses the HWID object into a more compact dict.

  This function returns the project name and binary string from the HWID object,
  along with a generated dict of components to their probed values decoded in
  the HWID object.

  Args:
    hwid: A decoded HWID object.

  Returns:
    A dict containing the project name, the binary string, and the list of
    components.
  """
  output_components = collections.defaultdict(list)
  components = hwid.bom.components
  db_components = hwid.database.components
  for comp_cls in sorted(components):
    for (comp_name, probed_values, _) in sorted(components[comp_cls]):
      if not probed_values:
        probed_values = db_components.GetComponentAttributes(
            comp_cls, comp_name).get('values')
      output_components[comp_cls].append(
          {comp_name: probed_values if probed_values else None})
  return {'project': hwid.database.project,
          'binary_string': hwid.binary_string,
          'image_id': hwid.database.image_id[hwid.bom.image_id],
          'components': dict(output_components)}


def VerifyHWID(db, encoded_string, probed_results, vpd=None, rma_mode=False,
               current_phase=None):
  """Verifies the given encoded HWID v3 string against the component db.

  A HWID context is built with the encoded HWID string and the project-specific
  component database. The HWID context is used to verify that the probed
  results match the infomation encoded in the HWID string.

  RO and RW VPD are also loaded and checked against the required values stored
  in the project-specific component database.

  Phase checks are enforced; see cros.factory.hwid.common.VerifyPhase for
  details.

  A set of mandatory rules for VPD are also forced here.

  Args:
    db: A Database object to be used.
    encoded_string: An encoded HWID string to test.
    probed_results: A dict containing the probed results to be used.
    vpd: None or a dict of RO and RW VPD values.  This argument should be set
        if some rules in the HWID database rely on the VPD values.
    rma_mode: True for RMA mode to allow deprecated components. Defaults to
        False.
    current_phase: The current phase, for phase checks.  If None is
        specified, then phase.GetPhase() is used (this defaults to PVT
        if none is available).

  Raises:
    HWIDException if verification fails.
  """
  hwid_mode = _HWIDMode(rma_mode)
  hwid = decoder.Decode(db, encoded_string, mode=hwid_mode)
  hwid.VerifyProbeResult(probed_results)
  hwid.VerifyComponentStatus(current_phase=current_phase)
  hwid.VerifyPhase(current_phase)
  context_args = dict(hwid=hwid)
  if vpd is not None:
    context_args['vpd'] = vpd
  context = rule.Context(**context_args)
  db.rules.EvaluateRules(context, namespace='verify.*')


def VerifyComponents(db, probed_results, component_list):
  """Verifies the given component list against the given HWID database.

  This function is to ensure the installed components are correct.  This method
  uses the HWID v3 component database to verify components.

  Args:
    db: A Database object to be used.
    probed_results: A dict containing the probed results to be verified.
    component_list: A list of components to verify. (e.g., ['cpu', 'video'])

  Returns:
    A dict from component class to a list of one or more
    ProbedComponentResult tuples.
    {component class: [ProbedComponentResult(
        component_name,  # The component name if found in the db, else None.
        probed_string,   # The actual probed string. None if probing failed.
        error)]}         # The error message if there is one.
  """
  return db.VerifyComponents(probed_results, component_list,
                             loose_matching=True)


def WriteHWID(encoded_string):
  """Writes the given encoded version 3 HWID string to firmware GBB section.

  Args:
    encoded_string: An encoded HWID string to write.
  """
  main_fw = crosfw.LoadMainFirmware()
  fw_filename = main_fw.GetFileName(sections=['GBB'])
  process_utils.Spawn(
      ['futility', 'gbb', '--set', '--hwid=%s' % encoded_string, fw_filename],
      check_call=True, log=True)
  main_fw.Write(fw_filename)


def ListComponents(db, comp_class=None):
  """Lists the components of the given component class.

  Args:
    db: A Database object to be used.
    comp_class: An optional list of component classes to look up. If not given,
        the function will list all the components of all component classes in
        the database.

  Returns:
    A dict of component classes to the component items of that class.
  """
  if not comp_class:
    comp_class_to_lookup = db.components.components_dict.keys()
  else:
    comp_class_to_lookup = type_utils.MakeList(comp_class)

  output_components = collections.defaultdict(list)
  for comp_cls in comp_class_to_lookup:
    if comp_cls not in db.components.components_dict:
      raise ValueError('Invalid component class %r' % comp_cls)
    output_components[comp_cls].extend(
        db.components.components_dict[comp_cls]['items'].keys())

  # Convert defaultdict to dict.
  return dict(output_components)


def EnumerateHWID(db, image_id=None, status='supported'):
  """Enumerates all the possible HWIDs.

  Args:
    db: A Database object to be used.
    image_id: The image ID to use.  Defaults to the latest image ID.
    status: By default only 'supported' components are enumerated.  Set this to
        'released' will include 'supported' and 'deprecated'. Set this to
        'all' if you want to include 'deprecated', 'unsupported' and
        'unqualified' components.

  Returns:
    A dict of all enumetated HWIDs to their list of components.
  """
  def _GenerateEncodedString(encoded_fields):
    """Generates encoded string by encoded_fields

    Args:
      encoded_fields: This parameter records indices of encoded fields
    """
    encoding_pattern = 0
    pass_check = True
    components = collections.defaultdict(list)
    component_list = []
    logging.debug('EnumerateHWID: Iterate encoded_fields %s',
                  ','.join(map(str, encoded_fields.values())))
    for field, index in encoded_fields.iteritems():
      # pylint: disable=W0212
      attr_dict = db._GetAttributesByIndex(field, index)
      comp_items = []
      for comp_cls, attr_list in attr_dict.iteritems():
        if attr_list is None:
          comp_items.append('None')
          components[comp_cls].append(common.ProbedComponentResult(
              None, None, common.MISSING_COMPONENT_ERROR(comp_cls)))
        else:
          for attrs in attr_list:
            if status == 'supported' and attrs.get('status') in (
                common.HWID.COMPONENT_STATUS.unsupported,
                common.HWID.COMPONENT_STATUS.deprecated,
                common.HWID.COMPONENT_STATUS.unqualified):
              pass_check = False
              logging.debug('Ignore %s.%s: %r', comp_cls, attrs['name'],
                            attrs['status'])
              break
            if status == 'released' and attrs.get('status') in (
                common.HWID.COMPONENT_STATUS.unsupported,
                common.HWID.COMPONENT_STATUS.unqualified):
              pass_check = False
              logging.debug('Ignore %s.%s: %r', comp_cls, attrs['name'],
                            attrs['status'])
              break
            comp_items.append(attrs['name'])
            components[comp_cls].append(common.ProbedComponentResult(
                attrs['name'], attrs['values'], None))
      component_list.append(' '.join(comp_items))
    if pass_check:
      bom = common.BOM(db.project, encoding_pattern, image_id, components,
                       encoded_fields)
      binary_string = encoder.BOMToBinaryString(db, bom)
      encoded_string = encoder.BinaryStringToEncodedString(db, binary_string)
      hwid_dict[encoded_string] = ','.join(component_list)

  def _RecursivelyGenerate(index=None, encoded_fields=None):
    """Recursive function to generate all combinations.

    Args:
      index: This parameter means the index of pattern fields
      encoded_fields: This parameter records index of components
    """
    if index >= len(fields_list):
      _GenerateEncodedString(encoded_fields)
      return

    field = fields_list[index]
    if field not in fields_bits.keys():
      encoded_fields[field] = 0
      _RecursivelyGenerate(index + 1, encoded_fields)
    else:
      for i in xrange(0, len(db.encoded_fields[field])):
        if i >= 2 ** fields_bits[field]:
          break
        encoded_fields[field] = i
        _RecursivelyGenerate(index + 1, encoded_fields)

  def _ConvertImageID(image_id=None):
    """Gets image ID.

    Args:
      image_id: The image ID.  It can be a number, a string, or None:
        1. If it's a number then return the number.
        2. If it's a string then look up the image ID in the database with it.
        3. If it's None, return the latest image ID.

    Returns:
      An integer of the image ID as defined in the database.
    """
    max_image_id = max(db.image_id.keys())
    if not isinstance(image_id, int):
      if image_id is None:
        image_id = max_image_id
      elif image_id.isdigit():
        image_id = int(image_id)
      else:
        for k, v in db.image_id.iteritems():
          if image_id == v:
            image_id = k
            break
    assert image_id in range(0, max_image_id + 1), 'Invalid Image ID'
    return image_id

  hwid_dict = {}
  encoded_fields = collections.defaultdict(int)
  image_id = _ConvertImageID(image_id)

  fields_bits = collections.defaultdict(int)
  for field in db.pattern.GetPatternByImageId(image_id)['fields']:
    comp, bit_width = field.items()[0]
    fields_bits[comp] += bit_width
  fields_list = db.encoded_fields.keys()

  # Recursively generate all combinations of HWID.
  _RecursivelyGenerate(0, encoded_fields)
  return hwid_dict


def GetProbedResults(infile=None, raw_data=None):
  """Get probed results from the given resources for the HWID framework.

  If `infile` is specified, the probe results will be obtained from that file.
  Otherwise if `raw_data` is specificed, the probe results will be obtained by
  decoding the raw data.

  Args:
    infile: None or the path of a file containing the probed results in JSON
        format.
    raw_data: None or a string of the raw data of the probed results.

  Returns:
    A dict of probed results.
  """
  if infile:
    return json_utils.LoadFile(infile)
  elif raw_data:
    return json_utils.LoadStr(raw_data)
  else:
    if sys_utils.InChroot():
      raise ValueError('Cannot probe components in chroot. Please specify '
                       'probed results with an input file. If you are running '
                       'with command-line, use --probed-results-file')
    # TODO(yhong): Probe with a project-specific probe statement instead of
    #     runing generic probe.
    cmd = 'gooftool probe'
    return json_utils.LoadStr(process_utils.CheckOutput(cmd, shell=True))


def GetDeviceInfo(infile):
  """Get device info from the given file.

  Args:
    infile: A file containing the device info in YAML format. For example:

        component.has_cellular: True
        component.keyboard: US_API
        ...

  Returns:
    A dict of device info.
  """
  with open(infile, 'r') as f:
    device_info = yaml.load(f.read())
  return device_info


def GetVPDData(run_vpd=False, vpd_data_file=None):
  """Get the vpd data for the context instance.

  Args:
    run_vpd: Whether to run `vpd` command-line tool to obtain the vpd data.
    vpd_data_file: Obtain the vpd data by reading the specified file if set.

  Returns:
    A dict of vpd data.  Empty if neither `run_vpd` nor `vpd_data_file` are
        specified.
  """
  assert not (run_vpd and vpd_data_file)
  if run_vpd:
    vpd_tool = sys_utils.VPDTool()
    return {
        'ro': vpd_tool.GetAllData(partition=vpd_tool.RO_PARTITION),
        'rw': vpd_tool.GetAllData(partition=vpd_tool.RW_PARTITION)
    }
  elif vpd_data_file:
    return json_utils.LoadFile(vpd_data_file)
  else:
    return {'ro': {}, 'rw': {}}


def GetHWIDString():
  """Get HWID string from GBB on a DUT."""
  if sys_utils.InChroot():
    raise ValueError('Cannot read HWID from GBB in chroot')
  main_fw_file = crosfw.LoadMainFirmware().GetFileName(sections=['GBB'])
  gbb_result = process_utils.CheckOutput(
      ['futility', 'gbb', '-g', '--hwid', '%s' % main_fw_file])
  return re.findall(r'hardware_id:(.*)', gbb_result)[0].strip()


def ComputeDatabaseChecksum(file_name):
  """Computes the checksum of the give database."""
  return database.Database.Checksum(file_name)
