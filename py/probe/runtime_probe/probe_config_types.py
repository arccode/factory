# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Defines classes to hold the definitions regarding to the probe config."""

import copy
import re

from cros.factory.utils import json_utils
from cros.factory.utils import type_utils


ValueType = type_utils.Enum(['INT', 'STRING'])

class OutputFieldDefinition:
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


class ProbeFunctionDefinition:
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


class ComponentProbeStatement:
  """Component probe statement with hash.

  In order to deduplicate probe statements, this class hashes fields without
  component name.  Therefore we can take some preference to choose one of
  components as the primary identifier among ComponentProbeStatement instances
  with same hash value.

  Attributes:
    category_name: A string of the HWID category.
    component_name: A string of the component name.
    statement: A nested dict generated from
        ProbeStatementDefinition.GenerateProbeStatement.
  """

  def __init__(self, category_name, component_name, statement):
    self._category_name = category_name
    self._component_name = component_name
    self._statement = statement
    self._statement_hash = hash(
        json_utils.DumpStr((category_name, statement), sort_keys=True))

  @property
  def category_name(self):
    return self._category_name

  @property
  def component_name(self):
    return self._component_name

  @property
  def statement(self):
    return self._statement

  @property
  def statement_hash(self):
    return self._statement_hash

  def __eq__(self, other):
    return isinstance(other, ComponentProbeStatement) and (
        self.statement_hash == other.statement_hash and
        self.component_name == other.component_name)

  def __repr__(self):
    return str({
        'component_name': self.component_name,
        'statement': self.statement
    })

  @classmethod
  def FromDict(cls, d):
    try:
      if len(d) != 1:
        raise ValueError(f'Only one category is allowed: {d!r}')
      category, probe_statement = next(iter(d.items()))
      if not isinstance(category, str):
        raise ValueError(f'Category is not a string: {category!r}')
      if len(probe_statement) != 1:
        raise ValueError(f'Only one component is allowed: {probe_statement!r}')
      component_name, statement = next(iter(probe_statement.items()))
      if not isinstance(component_name, str):
        raise ValueError(f'Component name is not a string: {component_name!r}')
      return cls(category, component_name, statement)
    except ValueError:
      raise
    except Exception as e:
      raise ValueError(f'Unexpected format for dict {d!r}') from e


class ProbeStatementDefinition:
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
      expected_fields: A list of dictionary which maps the field names to the
          expected values.
      probe_function_argument: A dictionary which will be passed to the probe
          function.

    Returns:
      A ComponentProbeStatement instance represents the generated probe
      statement.  If the length of the expected_fields is exactly 1, the value
      of "expect" could be a field record dictionary directly.
    """

    def GenerateExpectedFields(expected_fields):
      if isinstance(expected_fields, list):
        if len(expected_fields) == 1:
          return GenerateExpectedFields(expected_fields[0])
        return list(map(GenerateExpectedFields, expected_fields))
      return {
          k: self.expected_fields[k].probe_statement_generator(v)
          for k, v in expected_fields.items()
      }

    statement = {
        'eval': {
            probe_function_name: probe_function_argument or {}
        },
        'expect': GenerateExpectedFields(expected_fields)
    }
    if information is not None:
      statement['information'] = information
    return ComponentProbeStatement(self.category_name, component_name,
                                   statement)


class ProbeConfigPayload:
  """Placeholder for a probe config.

  In essence, a probe config payload contains a bunch of probe statement for
  each component.
  """
  def __init__(self):
    self._data = {}
    self._probe_statement_hash_values = set()

  def AddComponentProbeStatement(self, probe_statement):
    """Add a probe statement into this payload.

    Args:
      probe_statement: The probe statement to be added.

    Raises:
      `ValueError` if a confliction is found.
    """

    dest = self._data.setdefault(probe_statement.category_name, {})
    if probe_statement.component_name in dest:
      raise ValueError(
          'duplicated component: %s.%s' %
          (probe_statement.category_name, probe_statement.component_name))
    if probe_statement.statement_hash in self._probe_statement_hash_values:
      raise ValueError(
          'duplicated probe statement: %s.%s: %s' %
          (probe_statement.category_name, probe_statement.component_name,
           probe_statement.statement))
    self._probe_statement_hash_values.add(probe_statement.statement_hash)
    dest[probe_statement.component_name] = copy.deepcopy(
        probe_statement.statement)

  def DumpToString(self):
    return json_utils.DumpStr(self._data, pretty=True)


class _AbstractOutputFieldValue:
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
    if isinstance(value, self._REGEXP_TYPE):
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


class ProbeStatementDefinitionBuilder:
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
