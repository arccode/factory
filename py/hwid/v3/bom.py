# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""BOM class for HWID v3 framework."""

import copy

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import rule
from cros.factory.utils import schema


class BOM(object):
  """A class that holds all the information regarding a BOM.

  Attributes:
    project: A string of project name.
    encoding_pattern_index: An int indicating the encoding pattern. Currently,
        only 0 is used.
    image_id: An int indicating the image id.
    components: A dict that maps component classes to a list of
        ProbedComponentResult.
    encoded_fields: A dict that maps each encoded field to its index.

  Raises:
    SchemaException if invalid argument format is found.
  """
  _COMPONENTS_SCHEMA = schema.Dict(
      'bom',
      key_type=schema.Scalar('component class', str),
      value_type=schema.List(
          'list of ProbedComponentResult',
          schema.Tuple('ProbedComponentResult',
                       [schema.Optional(schema.Scalar('component name', str)),
                        schema.Optional(schema.Dict(
                            'probed_values',
                            key_type=schema.Scalar('key', str),
                            value_type=schema.AnyOf([
                                schema.Scalar('value', str),
                                schema.Scalar('value', rule.Value)]))),
                        schema.Optional(schema.Scalar('error', str))])))

  def __init__(self, project, encoding_pattern_index, image_id,
               components, encoded_fields):
    self.project = project
    self.encoding_pattern_index = encoding_pattern_index
    self.image_id = image_id
    self.components = components
    self.encoded_fields = encoded_fields
    BOM._COMPONENTS_SCHEMA.Validate(self.components)

  def Duplicate(self):
    """Duplicates this BOM object.

    Returns:
      A deepcopy of the original BOM object.
    """
    return copy.deepcopy(self)

  def __eq__(self, op2):
    if not isinstance(op2, BOM):
      return False
    return self.__dict__ == op2.__dict__

  def __ne__(self, op2):
    return not self.__eq__(op2)
