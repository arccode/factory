# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(yhong): Integrate the module with go/cros-probe.

import collections
import copy
import re

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
from cros.factory.utils import json_utils


class ProbeInfoParsedResult(object):
  """Placeholder for the parsed result of the given probe info.

  Properties:
    general_error_msg: `None` or a string of error message.
    probe_parameter_errors: `None` or a list of
        `stubby_pb2.ProbeParameterError`.
    probe_statement: `None` or a string of generated probe statement.
  """
  def __init__(self, general_error_msg, probe_parameter_errors,
               probe_statement):
    self.general_error_msg = general_error_msg
    self.probe_parameter_errors = probe_parameter_errors
    self.probe_statement = probe_statement

  @property
  def is_passed(self):
    """`True` iff no error is found from the probe parameters."""
    return not bool(self.general_error_msg or self.probe_parameter_errors)


class _ProbeParameterDescription(object):
  def __init__(self, description, pattern, error_msg, field_factory):
    self.description = description
    self.pattern = pattern
    self.error_msg = error_msg
    self.field_factory = field_factory

  @classmethod
  def GenerateHexValueInstance(cls, description, num_bits, error_msg=None):
    num_hex_digits = num_bits // 4
    pattern = re.compile('[0-9A-F]{%d}$' % num_hex_digits)
    error_msg = error_msg or (
        'Format error, should be a hex number between %s and %s with leading '
        'zeros preserved.' % ('0' * num_hex_digits, 'F' * num_hex_digits))
    field_factory = lambda value: [
        True, 'hex', '!eq 0x{value:0>{num_hex_digits}}'.format(
            value=value, num_hex_digits=num_hex_digits)]
    return cls(description, pattern, error_msg, field_factory)

  @classmethod
  def GenerateASCIIStringValueInstance(cls, description, value_len,
                                       error_msg=None):
    pattern = re.compile('[ -~]{%d}$' % value_len)
    error_msg = (error_msg
                 or 'Format error, must be %d ASCII characters.' % value_len)
    field_factory = lambda value: [True, 'str', '!eq %s' % value]
    return cls(description, pattern, error_msg, field_factory)


class _ProbeFunctionRepresentor(object):
  """Class that represents a probe function."""
  def __init__(self, component_type, probe_function_name,
               probe_function_description):
    """Constructor.

    Args:
      component_type: The component type the target probe function belongs to.
      probe_function_name: The name of the target probe function.
      probe_function_description: A string of the text description of the
          probe function.
    """
    self._component_type = component_type
    self._probe_function_name = probe_function_name
    self._probe_function_description = probe_function_description
    self._probe_param_infos = {}

  def AddProbeParameter(self, name, probe_parameter_description,
                        group_name=None):
    """Add a probe parameter.

    Args:
      name: Parameter name.
      probe_parameter_description: Instance of `_ProbeParameterDescription`
          that contains all detail about the probe parameter.
    """
    self._probe_param_infos[name] = (probe_parameter_description, group_name)

  def ExportProbeFunctionDefinition(self):
    """Returns the definition of the probe function."""
    ret = stubby_pb2.ProbeFunctionDefinition(
        name=self._probe_function_name,
        description=self._probe_function_description)
    for probe_param_name, probe_param_info in self._probe_param_infos.items():
      probe_param_desc, unused_group_name = probe_param_info
      ret.parameter_definitions.add(name=probe_param_name,
                                    description=probe_param_desc.description)
    return ret

  def IsThisProbeFunction(self, probe_function_name):
    """Returns `True` if the given probe function name matches this one.

    Args:
      probe_function_name: Name of the probe function to test.
    """
    return self._probe_function_name == probe_function_name

  def ParseProbeParameters(self, probe_parameters,
                           generate_probe_statement=None):
    """Parses the given probe parameters.

    If `generate_probe_statement` is not specified, the method validates
    the values of the given probe parameters.  Otherwise, it also generates
    the corresponding probe statement from the given data.

    Args:
      probe_parameters: A list of `stubby_pb2.ProbeParameter` to parse.
      generate_probe_statement: `None` or the component name of the probe
          statement to generate.

    Returns:
      An instance of `ProbeInfoParsedResult`.  The instance property
      `probe_statement` is conditionally set.

    Raises:
      `ValueError` if the given probe parameters contain unexpected data, i.e.
      not meet the probe function definition.
    """
    probe_params_by_name = collections.defaultdict(list)
    for probe_param in probe_parameters:
      if probe_param.name not in self._probe_param_infos:
        raise ValueError('Got unknown probe parameter %r for function %r.' %
                         (probe_param.name, self._probe_function_name))
      probe_params_by_name[probe_param.name].append(probe_param)

    ret = ProbeInfoParsedResult(None, [], None)

    matched_probe_param_group_names = set()
    probe_param_errors_by_group_name = collections.defaultdict(list)
    for probe_param_name, probe_param_info in self._probe_param_infos.items():
      probe_param_desc, group_name = probe_param_info
      probe_params = probe_params_by_name[probe_param_name]
      if len(probe_params) != 1:
        raise ValueError(
            'Expect exactly one probe parameter value for %s.%s, but got %d.' %
            (self._probe_function_name, probe_param_name, len(probe_params)))
      probe_param_value = probe_params[0].str_value
      if probe_param_value and group_name:
        matched_probe_param_group_names.add(group_name)
      if not probe_param_desc.pattern.match(probe_param_value):
        error_inst = stubby_pb2.ProbeParameterError(
            probe_parameter=copy.deepcopy(probe_params[0]),
            error_msg=probe_param_desc.error_msg)
        if group_name is None:
          ret.probe_parameter_errors.append(error_inst)
        else:
          probe_param_errors_by_group_name[group_name].append(
              error_inst)

    if not matched_probe_param_group_names:
      ret.general_error_msg = 'Missing HW interface specific probe parameters.'
      return ret

    if len(matched_probe_param_group_names) > 1 and generate_probe_statement:
      raise ValueError('Got inexplicit probe info, unable to select the '
                       'correct transform logic among %r.' %
                       matched_probe_param_group_names)

    for probe_param_group_name in matched_probe_param_group_names:
      ret.probe_parameter_errors += probe_param_errors_by_group_name[
          probe_param_group_name]

    if generate_probe_statement and not ret.probe_parameter_errors:
      ret.probe_statement = self._TransformProbeParametersToProbeStatement(
          generate_probe_statement, probe_params_by_name,
          matched_probe_param_group_names.pop())

    return ret

  def _TransformProbeParametersToProbeStatement(self, probe_statement_name,
                                                probe_params_by_name,
                                                probe_param_group_name):
    expect_field = {}
    accept_group_names = {None, probe_param_group_name}
    for probe_param_name, probe_param_info in self._probe_param_infos.items():
      probe_param_desc, group_name = probe_param_info
      if group_name in accept_group_names:
        expect_field[probe_param_name] = probe_param_desc.field_factory(
            probe_params_by_name[probe_param_name][0].str_value)
    return json_utils.DumpStr(
        {
            self._component_type: {
                probe_statement_name: {
                    "eval": {
                        self._probe_function_name: {}
                    },
                    "expect": expect_field
                }
            }
        },
        pretty=True)


def _GenerateStorageProbeFunctionRepresentor():
  storage_probe_func = _ProbeFunctionRepresentor(
      'storage', 'generic_storage',
      'Probe function for eMMC, ATA and NVMe storages.')

  storage_probe_func.AddProbeParameter(
      'manfid',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'Manufacturer ID (MID) in CID register of eMMC storages.', 8),
      group_name='mmc')
  storage_probe_func.AddProbeParameter(
      'oemid',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'OEM/Application ID (OID) in CID register of eMMC storages.', 16),
      group_name='mmc')
  storage_probe_func.AddProbeParameter(
      'name',
      _ProbeParameterDescription.GenerateASCIIStringValueInstance(
          'Product name (PNM) in CID register of eMMC storages.', 6),
      group_name='mmc')
  storage_probe_func.AddProbeParameter(
      'prv',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'Product revision (PRV) in CID register of eMMC storages.', 8),
      group_name='mmc')

  storage_probe_func.AddProbeParameter(
      'pci_vendor',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'PCI Vendor ID of NVMe storages.', 16), group_name='nvme')
  storage_probe_func.AddProbeParameter(
      'pci_device',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'PCI Device ID of NVMe storages.', 16), group_name='nvme')
  storage_probe_func.AddProbeParameter(
      'pci_class',
      _ProbeParameterDescription.GenerateHexValueInstance(
          'PCI Device Class Indicator of NVMe storages.', 32),
      group_name='nvme')

  storage_probe_func.AddProbeParameter(
      'ata_vendor',
      _ProbeParameterDescription.GenerateASCIIStringValueInstance(
          'Vendor name of SATA storages.', 8), group_name='ata')
  storage_probe_func.AddProbeParameter(
      'ata_model',
      _ProbeParameterDescription.GenerateASCIIStringValueInstance(
          'Model name of SATA storages.', 16), group_name='ata')

  return storage_probe_func


class ProbeToolManager(object):
  """Provides functionalities related to the probe tool."""
  def __init__(self):
    # TODO(yhong): Register all supported probe functions.
    self._probe_func_reprs = [
        _GenerateStorageProbeFunctionRepresentor()
    ]

  def GetProbeSchema(self):
    """
    Returns:
      The probe schema in format of the protobuf message.
    """
    ret = stubby_pb2.ProbeSchema()
    for probe_function_repr in self._probe_func_reprs:
      ret.probe_function_definitions.add().CopyFrom(
          probe_function_repr.ExportProbeFunctionDefinition())
    return ret

  def ValidateProbeInfo(self, probe_function_name, probe_parameters):
    """Validate the given probe info.

    Args:
      probe_function_name: Name of the probe function.
      probe_parameters: A list of `ProbeParameter`.

    Returns:
      An instance of `ProbeInfoParsedResult` which records detailed validation
      result.

    Raises:
      `ValueError` if the given data contain unexpected values.
    """
    probe_func_repr = self._LookupProbeFuncRepresentor(probe_function_name)
    return probe_func_repr.ParseProbeParameters(probe_parameters)

  def GenerateProbeStatement(self, probe_function_name, probe_parameters,
                             component_name):
    """Generate the corresponding probe statement from the given probe info.

    Args:
      probe_function_name: Name of the probe function.
      probe_parameters: A list of `ProbeParameter`.
      component_name: A string of the name of the component in the result
          probe statement.

    Returns:
      An instance of `ProbeInfoParsedResult` which records detailed validation
      result.

    Raises:
      `ValueError` if the given data contain unexpected values.
    """
    probe_func_repr = self._LookupProbeFuncRepresentor(probe_function_name)
    return probe_func_repr.ParseProbeParameters(
        probe_parameters, generate_probe_statement=component_name)

  def _LookupProbeFuncRepresentor(self, probe_function_name):
    for probe_function_repr in self._probe_func_reprs:
      if probe_function_repr.IsThisProbeFunction(probe_function_name):
        return probe_function_repr
    raise ValueError('Unknown probe function: %r.' % probe_function_name)
