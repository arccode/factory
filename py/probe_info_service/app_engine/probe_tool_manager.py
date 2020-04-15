# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import hashlib
import re

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module
from cros.factory.probe.runtime_probe import probe_config_definition
from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import json_utils


ProbeSchema = stubby_pb2.ProbeSchema
ProbeFunctionDefinition = stubby_pb2.ProbeFunctionDefinition
ProbeParameterValueType = stubby_pb2.ProbeParameterValueType
ProbeInfo = stubby_pb2.ProbeInfo
ProbeInfoParsedResult = stubby_pb2.ProbeInfoParsedResult
ProbeParameterSuggestion = stubby_pb2.ProbeParameterSuggestion
ProbeInfoTestResult = stubby_pb2.ProbeInfoTestResult


class _IncompatibleError(Exception):
  """Raised when the given input is incompatible with the probe tool."""


class _ParamValueConverter(object):
  """Converter for the input of the probe statement from the probe parameter.

  Properties:
    value_type: Enum item of `ProbeParameterValueType`.
  """

  def __init__(self, value_type_name, value_converter=None):
    self._probe_param_field_name = value_type_name + '_value'
    self._value_converter = value_converter or self._DummyValueConverter

    self.value_type = getattr(ProbeParameterValueType, value_type_name.upper())

  def ConvertValue(self, probe_parameter):
    """Converts the given probe parameter to the probe statement's value.

    Args:
      probe_parameter: The target `ProbeParameter` to convert from.

    Returns:
      A value that the probe statement generator accepts.

    Raises:
      - `ValueError` if the format of the given probe parameter value is
        incorrect.
      - `_IncompatibleError` on all unexpected failures.
    """
    which_one_of = probe_parameter.WhichOneof('value')
    if which_one_of not in (None, self._probe_param_field_name):
      raise _IncompatibleError('unexpected type %r' % which_one_of)

    return self._value_converter(
        getattr(probe_parameter, self._probe_param_field_name))

  @staticmethod
  def _DummyValueConverter(value):
    return value


class ProbeFunc(object):
  """Represents a probe function that exports to other services.

  Properties:
    name: A string of the name as the identifier of this function.
  """
  class _ProbeParam(object):
    def __init__(self, description, value_converter, ps_gen):
      self.description = description
      self.value_converter = value_converter
      self.ps_gen = ps_gen

  _DEFAULT_VALUE_TYPE_MAPPING = {
      probe_config_types.ValueType.INT: _ParamValueConverter('int'),
      probe_config_types.ValueType.STRING: _ParamValueConverter('string'),
  }

  def __init__(self, runtime_probe_category_name, runtime_probe_func_name,
               probe_params=None):
    self._ps_generator = probe_config_definition.GetProbeStatementDefinition(
        runtime_probe_category_name)
    self._probe_func_def = self._ps_generator.probe_functions[
        runtime_probe_func_name]

    self._probe_param_infos = {}
    probe_params = (probe_params or
                    {f.name: None for f in self._probe_func_def.output_fields})
    not_found_flag = object()
    for output_field in self._probe_func_def.output_fields:
      probe_param = probe_params.get(output_field.name, not_found_flag)
      if probe_param is not_found_flag:
        continue
      probe_param = (probe_param or
                     self._DEFAULT_VALUE_TYPE_MAPPING[output_field.value_type])
      self._probe_param_infos[output_field.name] = self._ProbeParam(
          output_field.description, probe_param,
          output_field.probe_statement_generator)

    self.name = runtime_probe_category_name + '.' + runtime_probe_func_name

  def GenerateProbeFunctionDefinition(self):
    """Returns the schema of this function."""
    ret = ProbeFunctionDefinition(name=self.name,
                                  description=self._probe_func_def.description)
    for probe_param_name, probe_param in self._probe_param_infos.items():
      ret.parameter_definitions.add(
          name=probe_param_name,
          description=probe_param.description,
          value_type=probe_param.value_converter.value_type)
    return ret

  def ParseProbeParams(self, probe_params, allow_missing_params,
                       comp_name_for_probe_statement=None):
    """Walk through the given probe parameters.

    The method first validate each probe parameter.  Then if specified,
    it also generates the probe statement from the given input.

    Args:
      probe_params: A list of `ProbeParameter` to validate.
      allow_missing_params: Whether missing required probe parameters is
          allowed.
      comp_name_for_probe_statement: If set, this method generates the probe
          statement with the specified component name when all probe parameters
          are valid.

    Returns:
      A pair of the following:
        - `ProbeInfoParsedResult`
        - A probe statement object or `None`.
    """
    probe_param_errors = []
    ps_expected_fields = {}
    try:
      for index, probe_param in enumerate(probe_params):
        if probe_param.name in ps_expected_fields:
          raise _IncompatibleError('found duplicated probe parameter: %r' %
                                   probe_param.name)
        try:
          value = self._ConvertProbeParamToProbeStatementValue(probe_param)
        except ValueError as e:
          ps_expected_fields[probe_param.name] = None
          probe_param_errors.append(
              ProbeParameterSuggestion(index=index, hint=str(e)))
        else:
          ps_expected_fields[probe_param.name] = value

      missing_param_names = (
          set(self._probe_param_infos.keys()) - set(ps_expected_fields.keys()))
      if missing_param_names and not allow_missing_params:
        raise _IncompatibleError('missing probe parameters: %r' %
                                 ', '.join(missing_param_names))
    except _IncompatibleError as e:
      return (
          ProbeInfoParsedResult(
              result_type=ProbeInfoParsedResult.INCOMPATIBLE_ERROR,
              general_error_msg=str(e)),
          None)

    if probe_param_errors:
      return (
          ProbeInfoParsedResult(
              result_type=ProbeInfoParsedResult.PROBE_PARAMETER_ERROR,
              probe_parameter_errors=probe_param_errors),
          None)

    ps = None
    if comp_name_for_probe_statement:
      try:
        ps = self._ps_generator.GenerateProbeStatement(
            comp_name_for_probe_statement, self._probe_func_def.name,
            ps_expected_fields)
      except Exception as e:
        return (
            ProbeInfoParsedResult(
                result_type=ProbeInfoParsedResult.UNKNOWN_ERROR,
                general_error_msg=str(e)),
            None)
    return ProbeInfoParsedResult(result_type=ProbeInfoParsedResult.PASSED), ps

  def _ConvertProbeParamToProbeStatementValue(self, probe_param):
    """Tries to convert the given `ProbeParameter` into the expected value in
    the probe statement.

    Args:
      probe_param: The target `ProbeParameter` message to convert.

    Returns:
      The converted value.

    Raises:
      - `ValueError` for any kind of formatting error.
      - `_IncompatibleError` for all other errors.
    """
    probe_param_info = self._probe_param_infos.get(probe_param.name)
    if probe_param_info is None:
      raise _IncompatibleError('unknown probe parameter: %r' % probe_param.name)

    try:
      value = probe_param_info.value_converter.ConvertValue(probe_param)
    except _IncompatibleError as e:
      raise _IncompatibleError('got improper probe parameter %r: %r' %
                               (probe_param.name, e))

    # Attempt to trigger the probe statement generator directly to see if
    # it's convertable.
    unused_ps = probe_param_info.ps_gen(value)

    return value


def _GetAllProbeFuncs():
  # TODO(yhong): Separate the data piece out the code logic.
  def _StringToRegexpOrString(value):
    PREFIX = '!re '
    if value.startswith(PREFIX):
      return re.compile(value.lstrip(PREFIX))
    return value

  return [
      ProbeFunc(
          'battery', 'generic_battery', {
              'manufacturer': _ParamValueConverter('string',
                                                   _StringToRegexpOrString),
              'model_name': _ParamValueConverter('string',
                                                 _StringToRegexpOrString),
          }),
      ProbeFunc(
          'storage', 'mmc_storage',
          {n: None for n in ['manfid', 'oemid', 'name', 'prv', 'sectors']}),
      ProbeFunc(
          'storage', 'nvme_storage',
          {n: None
           for n in ['pci_vendor', 'pci_device', 'pci_class', 'sectors']}),
  ]


class PayloadInvalidError(Exception):
  """Exception class raised when the given payload is invalid."""


class ProbeDataSource(object):
  """A record class for a source of probe statement and its metadata.

  Instances of this class are the source for generating the final probe
  bundle.  There are two ways to generate an instance:
    1. Convert from the probe info from other services.
    2. Load from the backend storage system.

  Properties:
    component_name: A string of the name of the component.
    probe_info: `None` or an instance of `ProbeInfo`.
    probe_info_fp: `None` or a string of the source probe info.
  """
  def __init__(self, component_name, probe_info, probe_info_fp):
    self.component_name = component_name
    self.probe_info = probe_info
    self.probe_info_fp = probe_info_fp


class QualProbeTestBundlePayloadGenerationResult(object):
  def __init__(self, probe_info_parsed_result, payload):
    self.probe_info_parsed_result = probe_info_parsed_result
    self.payload = payload


class ProbeToolManager(object):
  """Provides functionalities related to the probe tool."""

  _PROBE_INFO_FINGERPRINT_KEY = 'PROBE_INFO_FINGERPRINT'

  def __init__(self):
    self._probe_funcs = {pf.name: pf for pf in _GetAllProbeFuncs()}

  def GetProbeSchema(self):
    """
    Returns:
      An instance of `ProbeSchema`.
    """
    ret = ProbeSchema()
    for probe_func in self._probe_funcs.values():
      ret.probe_function_definitions.append(
          probe_func.GenerateProbeFunctionDefinition())
    return ret

  def ValidateProbeInfo(self, probe_info, allow_missing_params):
    """Validate the given probe info.

    Args:
      probe_info: An instance of `ProbeInfo` to be validated.
      allow_missing_params: Whether missing some probe parameters is allowed
          or not.

    Returns:
      An instance of `ProbeInfoParsedResult` which records detailed validation
      result.
    """
    probe_info_parsed_result, probe_func = self._LookupProbeFunc(
        probe_info.probe_function_name)
    if probe_func:
      probe_info_parsed_result, unused_ps = probe_func.ParseProbeParams(
          probe_info.probe_parameters, allow_missing_params)
    return probe_info_parsed_result

  def CreateProbeDataSourceFromProbeInfo(self, component_name, probe_info):
    return ProbeDataSource(component_name, probe_info,
                           self._CalcProbeInfoFingerprint(probe_info))

  def GenerateQualProbeTestBundlePayload(self, probe_data_source):
    """Generates the payload for testing the probe info of a qualification.

    Args:
      probe_data_source: The source of the test bundle.

    Returns:
      An instance of `QualProbeTestBundlePayloadGenerationResult`.
    """
    if probe_data_source.probe_info is None:
      raise NotImplementedError

    ret = QualProbeTestBundlePayloadGenerationResult(None, None)
    ret.probe_info_parsed_result, probe_func = self._LookupProbeFunc(
        probe_data_source.probe_info.probe_function_name)
    if probe_func:
      ret.probe_info_parsed_result, ps = probe_func.ParseProbeParams(
          probe_data_source.probe_info.probe_parameters, False,
          comp_name_for_probe_statement=probe_data_source.component_name)
    if ps is not None:
      # Inject probe info fingerprint into the `information` field so that
      # we can extract it back in the probe result payload.
      for category_ps in ps.values():
        for comp_name, comp_ps in category_ps.items():
          if comp_name == probe_data_source.component_name:
            information_field = comp_ps.setdefault('information', {})
            information_field[self._PROBE_INFO_FINGERPRINT_KEY] = (
                probe_data_source.probe_info_fp)
      builder = probe_config_types.ProbeConfigPayload()
      builder.AddComponentProbeStatement(ps)
      ret.payload = builder.DumpToString().encode('utf-8')

    return ret

  def AnalyzeQualProbeTestResultPayload(
      self, probe_data_source, probe_result_payload):
    """Analyzes the given probe result payload for a qualification.

    Args:
      probe_data_source: The original source for the probe statement.
      probe_result_payload: A byte string of the payload to be analyzed.

    Returns:
      An instance of `ProbeInfoTestResult`.

    Raises:
      `PayloadInvalidError` if the given input is invalid.
    """
    if probe_data_source.probe_info is None:
      raise NotImplementedError

    comp_probe_results = []
    try:
      probed_result = json_utils.LoadStr(probe_result_payload.decode('utf-8'))
      for category_pr in probed_result.values():
        comp_probe_results.extend(
            category_pr.get(probe_data_source.component_name, []))
    except Exception as e:
      raise PayloadInvalidError('Unable to load and parse the content: %s' % e)
    if not comp_probe_results:
      return ProbeInfoTestResult(
          result_type=ProbeInfoTestResult.INTRIVIAL_ERROR,
          intrivial_error_msg='No component is found.')
    comp_probe_result = comp_probe_results[0]
    try:
      fp = comp_probe_result['information'][self._PROBE_INFO_FINGERPRINT_KEY]
    except Exception as e:
      raise NotImplementedError

    if fp != probe_data_source.probe_info_fp:
      return ProbeInfoTestResult(result_type=ProbeInfoTestResult.LEGACY)
    return ProbeInfoTestResult(result_type=ProbeInfoTestResult.PASSED)

  def _LookupProbeFunc(self, probe_function_name):
    """A helper method to find the probe function instance by name.

    When the target probe function doesn't exist, the method creates and
    returns a `ProbeInfoParsedResult` message so that the caller merely
    needs to forward the error message without constructing it.

    Args:
      probe_function_name: A string of name of the target probe function.

    Returns:
      A pair of the following:
        - An instance of `ProbeInfoParsedResult` if not found; otherwise `None`.
        - An instance of `ProbeFunc` if found; otherwise `None`.
    """
    probe_func = self._probe_funcs.get(probe_function_name)
    if probe_func:
      parsed_result = None
    else:
      parsed_result = ProbeInfoParsedResult(
          result_type=ProbeInfoParsedResult.ResultType.INCOMPATIBLE_ERROR,
          general_error_msg='unknown probe function: %r' % probe_function_name)
    return parsed_result, probe_func

  def _CalcProbeInfoFingerprint(self, probe_info):
    """Derives a fingerprint string for the given probe info.

    Args:
      probe_info: An instance of `ProbeInfo` to be validated.

    Returns:
      A string of the fingerprint.
    """
    probe_param_values = {}
    for probe_param in probe_info.probe_parameters:
      probe_param_values.setdefault(probe_param.name, [])
      value_attr_name = probe_param.WhichOneof('value')
      probe_param_values[probe_param.name].append(
          getattr(probe_param, value_attr_name) if value_attr_name else None)
    serializable_data = {
        'probe_function_name': probe_info.probe_function_name,
        'probe_parameters':
            {k: sorted(v) for k, v in probe_param_values.items()},
    }
    hash_engine = hashlib.sha1()
    hash_engine.update(
        json_utils.DumpStr(serializable_data, sort_keys=True).encode('utf-8'))
    return hash_engine.hexdigest()
