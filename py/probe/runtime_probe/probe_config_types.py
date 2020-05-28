# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Defines classes to hold the definitions regarding to the probe config."""

import copy
import re

from cros.factory.utils import json_utils
from cros.factory.utils import type_utils


ValueType = type_utils.Enum(['INT', 'STRING'])

class OutputFieldDefinition(object):
  """Placeholder for the definition of a field outputted by a probe function.

  Attributes:
    name: A string of the name of this field.
    descripion: A string of the human-readable description of the meaning of
        this field.
    value_type: Enum item of `ValueType`.
    probe_statement_generator: A callable instance that converts the given
        value to a snippet of the probe statement for the expect-field section.
        It should perform validation among the value first and raise
        `ValueError` on failure.
  """
  def __init__(self, name, description, value_type, probe_statement_generator):
    self.name = name
    self.description = description
    self.value_type = value_type
    self.probe_statement_generator = probe_statement_generator


class ProbeFunctionDefinition(object):
  """Placeholder for the info. of a probe function.

  Attributes:
    name: A string of the name of the probe function.
    description: A string of the human-readable description of the probe
        function.
    output_fields: A list of `OutputFieldDefinition` instances that represents
        all the fields that would receive by invoking the probe function.
  """
  def __init__(self, name, description, output_fields):
    self.name = name
    self.description = description
    self.output_fields = output_fields


class ProbeStatementDefinition(object):
  """Probe statement generator of a specific component category.

  Attributes:
    category_name: A string of the name of the component category.
    probe_functions: A dictionary which records all available probe functions
        for this component category.  It maps the probe function name to
        the instance of `ProbeFunctionDefinition`.
    expected_fields: A dictionary which records all the available expected
        fields.  It maps the field name to the instance of
        `OutputFieldDefinition`.
  """
  def __init__(self, category_name, probe_functions, expected_fields):
    self.category_name = category_name
    self.probe_functions = probe_functions
    self.expected_fields = expected_fields

  def GenerateProbeStatement(self, component_name, probe_function_name,
                             expected_fields, probe_function_argument=None,
                             information=None):
    """Generate the probe statement from the given inputs.

    The term "probe config" represents to a huge payload that contains a bunch
    of probe statements for different components.  The return value of this
    method only represents to the probe statement of a single component.  One
    can use the helper function `MergeProbeStatements` to add it to the final
    probe config.

    Args:
      component_name: A string of the name of the component.
      probe_function_name: A string of the name of the probe function to use.
      expected_fields: A dictionary maps the field names to the expected values.
      probe_function_argument: A dictionary which will be passed to the probe
          function.

    Returns:
      An object represents the generated probe statement.
    """
    statement = {
        'eval': {
            probe_function_name: probe_function_argument or {}
        },
        'expect': {
            k: self.expected_fields[k].probe_statement_generator(v)
            for k, v in expected_fields.items()
        }
    }
    if information is not None:
      statement['information'] = information
    return {self.category_name: {component_name: statement}}


class ProbeConfigPayload(object):
  """Placeholder for a probe config.

  In essence, a probe config payload contains a bunch of probe statement for
  each component.
  """
  def __init__(self):
    self._data = {}

  def AddComponentProbeStatement(self, probe_statement):
    """Add a probe statement into this payload.

    Args:
      probe_statement: The probe statement to be added.

    Raises:
      `ValueError` if a confliction is found.
    """
    for comp_category, category_probe_statement in probe_statement.items():
      dest = self._data.setdefault(comp_category, {})
      for comp_name, comp_probe_statement in category_probe_statement.items():
        if comp_name in dest:
          raise ValueError(
              'duplicated component: %s.%s' % (comp_category, comp_name))
        dest[comp_name] = copy.deepcopy(comp_probe_statement)

  def DumpToString(self):
    return json_utils.DumpStr(self._data, pretty=True)


class _AbstractOutputFieldValue(object):
  """Base class for performing validation for a value of expected field.

  Class attributes:
    TYPE_TAG: A string of the type name of the value.
  """

  TYPE_TAG = None

  def GenerateProbeStatement(self, value=None):
    """Validate the given value by trying to generate the probe statement.

    Args:
      value: The value to be checked.

    Returns:
      The probe statement snippet for the expected field of this value.

    Raises:
      `TypeError` if the given `value` type is incorrect.
      `ValueError` if the given `value` is considered invalid.
    """
    if value is None:
      return [False, self.TYPE_TAG]
    return [True, self.TYPE_TAG, self._GenerateValueNotation(value)]

  def _GenerateValueNotation(self, value):
    """Validate the given value by trying to generate the notation of the given
    value in the probe statement.

    Args:
      value: The value to be checked.

    Returns:
      The probe statement snippet for the expected field of this value.

    Raises:
      `TypeError` if the given `value` type is incorrect.
      `ValueError` if the given `value` is considered invalid.
    """
    raise NotImplementedError

  def _GenerateTypeError(self, value):
    """A helper class for the sub class to generate the exception."""
    return TypeError('unknown value type %r for %r' % (type(value),
                                                       self.TYPE_TAG))


class _IntOutputFieldValue(_AbstractOutputFieldValue):
  TYPE_TAG = 'int'

  @type_utils.Overrides
  def _GenerateValueNotation(self, value):
    if isinstance(value, int):
      return '!eq %d' % value
    raise self._GenerateTypeError(value)


class _StrOutputFieldValue(_AbstractOutputFieldValue):
  TYPE_TAG = 'str'
  _REGEXP_TYPE = type(re.compile(''))

  def __init__(self, pattern=None, format_error_msg=None):
    self._pattern = pattern
    if self._pattern:
      self._format_error_msg = (
          format_error_msg or
          ('format error, the value is expected to match %r' %
           self._pattern.pattern))
    else:
      self._format_error_msg = None

  @type_utils.Overrides
  def _GenerateValueNotation(self, value):
    if isinstance(value, str):
      if self._pattern and not self._pattern.match(value):
        raise ValueError(self._format_error_msg)
      return '!eq %s' % value
    elif isinstance(value, self._REGEXP_TYPE):
      return '!re %s' % value.pattern
    raise self._GenerateTypeError(value)


class _HexOutputFieldValue(_AbstractOutputFieldValue):
  TYPE_TAG = 'hex'

  def __init__(self, num_digits=None):
    if num_digits is None:
      self._pattern = re.compile('^[0-9A-F]+$')
      self._format_error_msg = (
          'format error, should be a hex number constructs with 0-9, A-F')
    else:
      self._pattern = re.compile('^[0-9A-F]{%d}$' % num_digits)
      self._format_error_msg = (
          'format error, should be hex number between %s and %s with leading '
          'zero perserved.' % ('0' * num_digits, 'F' * num_digits))

  @type_utils.Overrides
  def _GenerateValueNotation(self, value):
    if isinstance(value, str):
      if self._pattern and not self._pattern.match(value):
        raise ValueError(self._format_error_msg)
      return '!eq 0x%s' % value
    raise self._GenerateTypeError(value)


class ProbeStatementDefinitionBuilder(object):
  """Helper class to build an instance of `ProbeStatementDefinition`."""
  ALL_PROBE_FUNCTIONS = object()

  def __init__(self, category_name):
    """Constructor.

    Args:
      category_name: A string of the name of the target component category.
    """
    self._category_name = category_name
    self._probe_function_descriptions = {}
    self._output_fields = []

  def AddProbeFunction(self, name, description):
    """Register a probe function.

    Args:
      name: A string of the name of the probe function.
      description: A string of the description of the probe function.
    """
    self._probe_function_descriptions[name] = description

  def AddOutputField(self, name, description, value_type,
                     probe_statement_generator, probe_function_names=None):
    """Add an output field.

    Args:
      name: A string of the name of the field.
      description: Description of the field.
      value_type: Type of the value of this output field, must be the enum
          item of `ValueType`.
      probe_statement_generator: A callable instance that generates the probe
          statement snippet from the given value for the expect-field part.
      probe_function_names: Specifying the probe functions that has this
          field.  Default to all functions.
    """
    if probe_function_names is None:
      probe_function_names = self.ALL_PROBE_FUNCTIONS
    output_field_definition = OutputFieldDefinition(
        name, description, value_type, probe_statement_generator)
    self._output_fields.append((output_field_definition, probe_function_names))

  def AddStrOutputField(self, name, description, probe_function_names=None,
                        value_pattern=None, value_format_error_msg=None):
    field_value = _StrOutputFieldValue(
        pattern=value_pattern, format_error_msg=value_format_error_msg)
    return self.AddOutputField(
        name, description, ValueType.STRING, field_value.GenerateProbeStatement,
        probe_function_names=probe_function_names)

  def AddHexOutputField(self, name, description, probe_function_names=None,
                        num_value_digits=None):
    field_value = _HexOutputFieldValue(num_digits=num_value_digits)
    return self.AddOutputField(
        name, description, ValueType.STRING, field_value.GenerateProbeStatement,
        probe_function_names=probe_function_names)

  def AddIntOutputField(self, name, description, probe_function_names=None):
    field_value = _IntOutputFieldValue()
    return self.AddOutputField(
        name, description, ValueType.INT, field_value.GenerateProbeStatement,
        probe_function_names=probe_function_names)

  def Build(self):
    probe_function_fields = {n : [] for n in self._probe_function_descriptions}
    for field_info, probe_function_names in self._output_fields:
      if probe_function_names is self.ALL_PROBE_FUNCTIONS:
        probe_function_names = list(self._probe_function_descriptions.keys())
      for probe_function_name in probe_function_names:
        probe_function_fields[probe_function_name].append(field_info)
    probe_functions = {
        n: ProbeFunctionDefinition(n, d, probe_function_fields[n])
        for n, d in self._probe_function_descriptions.items()
    }
    return ProbeStatementDefinition(self._category_name, probe_functions, {
        field_info.name : field_info
        for field_info, unused_probe_function_names in self._output_fields
    })
