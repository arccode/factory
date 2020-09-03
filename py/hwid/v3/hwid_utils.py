# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID v3 utility functions."""

import collections
import logging
import os

from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import identity as identity_utils
from cros.factory.hwid.v3.identity import Identity
from cros.factory.hwid.v3.rule import Context
from cros.factory.hwid.v3.configless_fields import ConfiglessFields
from cros.factory.hwid.v3 import transformer
from cros.factory.hwid.v3 import verifier
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import json_utils
from cros.factory.utils import type_utils


def _HWIDMode(rma_mode):
  if rma_mode:
    return common.OPERATION_MODE.rma
  return common.OPERATION_MODE.normal


def GenerateHWID(database, probed_results, device_info, vpd, rma_mode,
                 with_configless_fields, brand_code,
                 allow_mismatched_components=False, use_name_match=False):
  """Generates a HWID v3 from the given data.

  The HWID is generated based on the given device info and a BOM object. If
  there are conflits of component information between device_info and
  bom, priority is given to device_info.

  Args:
    database: A Database object to be used.
    probed_results: The probed results of the DUT.
    device_info: A dict of component infomation keys to their
        corresponding values. The format is device-specific and the meanings of
        each key and value vary from device to device. The valid keys and values
        should be specified in project-specific component database.
    vpd: A dict of RO and RW VPD values.  This argument should be set
        if some rules in the HWID database rely on the VPD values.
    rma_mode: Whether to verify components status in RMA mode.
    with_configless_fields: Whether to include configless fields.
    brand_code: None or a string of Chromebook brand code.
    allow_mismatched_components: Whether to allows some probed components to be
        ignored if no any component in the database matches with them.
    use_name_match: Use component name from probed results as matched component.

  Returns:
    The generated HWID Identity object.
  """
  from cros.factory.hwid.v3 import probe

  hwid_mode = _HWIDMode(rma_mode)

  bom = probe.GenerateBOMFromProbedResults(
      database, probed_results, device_info, vpd, hwid_mode,
      allow_mismatched_components, use_name_match)[0]
  verifier.VerifyComponentStatus(database, bom, hwid_mode)

  encoded_configless = None
  if with_configless_fields:
    encoded_configless = ConfiglessFields.Encode(
        database, bom, device_info, 0, rma_mode)

  identity = transformer.BOMToIdentity(database, bom, brand_code,
                                       encoded_configless)
  return identity


def DecodeHWID(database, encoded_string):
  """Decodes the given HWID v3 encoded string into a BOM object.

  Args:
    database: A Database object to be used.
    encoded_string: An encoded HWID string to test.

  Returns:
    The corresponding Identity object of the given `encoded_string`, the
        decoded BOM object and decoded configless fields.
  """
  image_id = identity_utils.GetImageIdFromEncodedString(encoded_string)
  encoding_scheme = database.GetEncodingScheme(image_id)
  identity = Identity.GenerateFromEncodedString(encoding_scheme, encoded_string)
  bom = transformer.IdentityToBOM(database, identity)

  configless_fields = None
  if identity.encoded_configless:
    configless_fields = ConfiglessFields.Decode(identity.encoded_configless)

  return identity, bom, configless_fields


def VerifyHWID(database, encoded_string,
               probed_results, device_info, vpd, rma_mode,
               current_phase=None, allow_mismatched_components=False):
  """Verifies the given encoded HWID v3 string against the probed BOM object.

  A HWID context is built with the encoded HWID string and the project-specific
  component database. The HWID context is used to verify that the probed
  results match the infomation encoded in the HWID string.

  RO and RW VPD are also loaded and checked against the required values stored
  in the project-specific component database.

  Phase checks are enforced; see cros.factory.hwid.v3.verifier.VerifyPhase for
  details.

  A set of mandatory rules for VPD are also forced here.

  Args:
    database: A Database object to be used.
    encoded_string: An encoded HWID string to test.
    probed_results: The probed results of the DUT.
    device_info: A dict of component infomation keys to their
        corresponding values. The format is device-specific and the meanings of
        each key and value vary from device to device. The valid keys and values
        should be specified in project-specific component database.
    vpd: A dict of RO and RW VPD values.  This argument should be set
        if some rules in the HWID database rely on the VPD values.
    rma_mode: True for RMA mode to allow deprecated components.
    current_phase: The current phase, for phase checks.  If None is
        specified, then phase.GetPhase() is used (this defaults to PVT
        if none is available).
    allow_mismatched_components: Whether to allows some probed components to be
        ignored if no any component in the database matches with them.

  Raises:
    HWIDException if verification fails.
  """
  from cros.factory.hwid.v3 import probe

  hwid_mode = _HWIDMode(rma_mode)

  probed_bom = probe.GenerateBOMFromProbedResults(
      database, probed_results, device_info, vpd, hwid_mode,
      allow_mismatched_components)[0]

  unused_identity, decoded_bom, decoded_configless = DecodeHWID(
      database, encoded_string)

  verifier.VerifyBOM(database, decoded_bom, probed_bom)
  verifier.VerifyComponentStatus(
      database, decoded_bom, hwid_mode, current_phase=current_phase)
  verifier.VerifyPhase(database, decoded_bom, current_phase, rma_mode)
  if decoded_configless:
    verifier.VerifyConfigless(
        database, decoded_configless, probed_bom, device_info, rma_mode)

  context = Context(
      database=database, bom=decoded_bom, mode=hwid_mode, vpd=vpd)
  for rule in database.verify_rules:
    rule.Evaluate(context)


def ListComponents(database, comp_class=None):
  """Lists the components of the given component class.

  Args:
    database: A Database object to be used.
    comp_class: An optional list of component classes to look up. If not given,
        the function will list all the components of all component classes in
        the database.

  Returns:
    A dict of component classes to the component items of that class.
  """
  if not comp_class:
    comp_class_to_lookup = database.GetComponentClasses()
  else:
    comp_class_to_lookup = type_utils.MakeList(comp_class)

  output_components = collections.defaultdict(list)
  for comp_cls in comp_class_to_lookup:
    if comp_cls not in database.GetComponentClasses():
      raise ValueError('Invalid component class %r' % comp_cls)
    output_components[comp_cls].extend(database.GetComponents(comp_cls).keys())

  # Convert defaultdict to dict.
  return dict(output_components)


def EnumerateHWID(database, image_id=None, status='supported', comps=None,
                  brand_code=None):
  """Enumerates all the possible HWIDs.

  Args:
    database: A Database object to be used.
    image_id: The image ID to use.  Defaults to the latest image ID.
    status: By default only 'supported' components are enumerated.  Set this to
        'released' will include 'supported' and 'deprecated'. Set this to
        'all' if you want to include 'deprecated', 'unsupported' and
        'unqualified' components.
    comps: None or a dict of list of string as the limit to specified
        components.

  Returns:
    A dict of all enumetated HWIDs to their list of components.
  """
  limited_comps = comps or {}

  if image_id is None:
    image_id = database.max_image_id

  if status == 'supported':
    acceptable_status = set([common.COMPONENT_STATUS.supported])
  elif status == 'released':
    acceptable_status = set([common.COMPONENT_STATUS.supported,
                             common.COMPONENT_STATUS.deprecated])
  elif status == 'all':
    acceptable_status = set(common.COMPONENT_STATUS)
  else:
    raise ValueError('The argument `status` must be one of "supported", '
                     '"released", "all", but got %r.' % status)

  def _IsComponentsSetValid(comps):
    for comp_cls, comp_names in comps.items():
      comp_names = type_utils.MakeList(comp_names)
      if (comp_cls in limited_comps and
          sorted(list(limited_comps[comp_cls])) != sorted(comp_names)):
        return False
      for comp_name in comp_names:
        status = database.GetComponents(comp_cls)[comp_name].status
        if status not in acceptable_status:
          return False
    return True

  results = {}
  def _RecordResult(components):
    bom = BOM(0, image_id, components)
    identity = transformer.BOMToIdentity(database, bom, brand_code=brand_code)
    results[identity.encoded_string] = bom

  def _RecursivelyEnumerateCombinations(combinations, i,
                                        selected_combinations):
    if i >= len(combinations):
      components = {}
      for selected_combination in selected_combinations:
        components.update(selected_combination)

      _RecordResult(components)
      return

    for combination in combinations[i]:
      selected_combinations[i] = combination
      _RecursivelyEnumerateCombinations(
          combinations, i + 1, selected_combinations)

  combinations = []
  for field_name, bit_length in database.GetEncodedFieldsBitLength(
      image_id).items():
    max_index = (1 << bit_length) - 1
    last_combinations = []
    for index, comps_set in database.GetEncodedField(field_name).items():
      if index <= max_index and _IsComponentsSetValid(comps_set):
        last_combinations.append(
            {comp_cls: type_utils.MakeList(comp_names)
             for comp_cls, comp_names in comps_set.items()})

    if not last_combinations:
      return {}
    combinations.append(last_combinations)

  _RecursivelyEnumerateCombinations(combinations, 0, [None] * len(combinations))
  return results


def GetProbedResults(infile=None, raw_data=None, project=None):
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
  if raw_data:
    return json_utils.LoadStr(raw_data)

  from cros.factory.hwid.v3 import probe
  from cros.factory.utils import sys_utils
  if sys_utils.InChroot():
    raise ValueError('Cannot probe components in chroot. Please specify '
                     'probed results with an input file. If you are running '
                     'with command-line, use --probed-results-file')
  probe_statement_path = GetProbeStatementPath(project)
  return probe.ProbeDUT(probe_statement_path)


def GetDeviceInfo(infile=None):
  """Get device info from the given file.

  Args:
    infile: A file containing the device info in YAML format. For example:

        component.has_cellular: True
        component.keyboard: US_API
        ...

  Returns:
    A dict of device info.
  """
  if infile:
    with open(infile, 'r') as f:
      return yaml.load(f.read())

  try:
    from cros.factory.test import device_data
    return device_data.GetAllDeviceData()

  except ImportError:
    return {}


def GetVPDData(run_vpd=False, infile=None):
  """Get the vpd data for the context instance.

  Args:
    run_vpd: Whether to run `vpd` command-line tool to obtain the vpd data.
    infile: Obtain the vpd data by reading the specified file if set.

  Returns:
    A dict of vpd data.  Empty if neither `run_vpd` nor `infile` are
        specified.
  """
  assert not (run_vpd and infile)
  if run_vpd:
    from cros.factory.gooftool import vpd
    vpd_tool = vpd.VPDTool()
    return {
        'ro': vpd_tool.GetAllData(partition=vpd.VPD_READONLY_PARTITION_NAME),
        'rw': vpd_tool.GetAllData(partition=vpd.VPD_READWRITE_PARTITION_NAME)
    }
  if infile:
    return json_utils.LoadFile(infile)
  return {'ro': {}, 'rw': {}}


def ComputeDatabaseChecksum(file_name):
  """Computes the checksum of the give database."""
  return Database.Checksum(file_name)


def ProbeProject():
  """Probes the project name.

  This function will try to run the command `cros_config / name` to get the
  project name.  If failed, this function will return the board name as legacy
  chromebook projects used to assume that the board name is equal to the
  project name.

  Returns:
    The probed project name as a string.
  """
  import subprocess

  from cros.factory.gooftool import cros_config as cros_config_module
  from cros.factory.utils import cros_board_utils


  try:
    cros_config = cros_config_module.CrosConfig()
    project = cros_config.GetModelName().lower()
    if project:
      return project

  except subprocess.CalledProcessError:
    pass

  return cros_board_utils.BuildBoard().short_name


def ProbeBrandCode():
  """Probes the brand code.

  This function will run the command `cros_config / brand-code` to get the brand
  code.

  Returns:
    The probed brand code as a string.
  """
  from cros.factory.gooftool import cros_config as cros_config_module
  from cros.factory.utils import sys_utils

  if sys_utils.InChroot():
    raise ValueError('Cannot probe brand code in chroot. Please use '
                     '--brand-code to specify brand code.')

  cros_config = cros_config_module.CrosConfig()

  return cros_config.GetBrandCode()


_HWID_REPO_PATH = None


def GetHWIDRepoPath():
  """Returns the path to the repository which holds all the HWID databases."""
  from cros.factory.utils import sys_utils
  assert sys_utils.InChroot()

  global _HWID_REPO_PATH  # pylint: disable=global-statement
  if _HWID_REPO_PATH is None:
    _HWID_REPO_PATH = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform', 'chromeos-hwid')
  return _HWID_REPO_PATH


_DEFAULT_DATA_PATH = None


def GetDefaultDataPath():
  """Returns the expected location of HWID data within a factory image or the
  chroot.
  """
  from cros.factory.utils import sys_utils

  global _DEFAULT_DATA_PATH  # pylint: disable=global-statement
  if _DEFAULT_DATA_PATH is None:
    if sys_utils.InChroot():
      _DEFAULT_DATA_PATH = os.path.join(GetHWIDRepoPath(), 'v3')
    else:
      _DEFAULT_DATA_PATH = '/usr/local/factory/hwid'
  return _DEFAULT_DATA_PATH


def GetHWIDBundleName(project=None):
  """Returns the filename of the hwid bundle

  Args:
    project: The project name.

  Returns:
    Filename of the hwid bundle name as a string.
  """
  project = project or ProbeProject()
  return 'hwid_v3_bundle_%s.sh' % project.upper()


def GetBrandCode(brand_code=None):
  brand_code = brand_code or ProbeBrandCode()
  return brand_code.upper()


def GetProbeStatementPath(project=None):
  path = os.path.join(os.path.dirname(__file__), common.DEFAULT_PROBE_STATEMENT)

  try:
    project = project or ProbeProject()
    # We assume that project name is not 'default'.
    model_probe_statement_path = os.path.join(
        os.path.dirname(__file__),
        '%s_probe_statement.json' % (project.lower()))
    if os.path.exists(model_probe_statement_path):
      path = model_probe_statement_path
  except Exception:
    logging.warning('Error while looking for project specific probe statement',
                    exc_info=True)
  return path
