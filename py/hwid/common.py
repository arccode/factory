# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common classes for HWID v3 operation."""

import collections
import copy
import os
import pprint
import re

import factory_common # pylint: disable=W0611
from cros.factory import common, schema, rule
from cros.factory.test import utils

# The expected location of HWID data within a factory image or the
# chroot.
DEFAULT_HWID_DATA_PATH = (
    os.path.join(os.environ['CROS_WORKON_SRCROOT'],
                 'src', 'platform', 'chromeos-hwid', 'v3')
    if utils.in_chroot()
    else '/usr/local/factory/hwid')


def ProbeBoard():
  """Probes the board name by looking up the CHROMEOS_RELEASE_BOARD variable
  in /etc/lsb-release.

  Returns:
    The probed board name as a string.

  Raises:
    HWIDException when probe error.
  """
  LSB_RELEASE_FILE = '/etc/lsb-release'
  LSB_BOARD_RE = re.compile(r'^CHROMEOS_RELEASE_BOARD=(\w+)$', re.M)
  if utils.in_chroot():
    raise HWIDException('Unable to determine board in chroot')
  if not os.path.exists(LSB_RELEASE_FILE):
    raise HWIDException('%r does not exist, unable to determine board' %
                        LSB_RELEASE_FILE)
  try:
    with open(LSB_RELEASE_FILE) as f:
      board = LSB_BOARD_RE.findall(f.read())[0].rpartition('_')[-1]
  except IndexError:
    raise HWIDException('Cannot determine board from %r' % LSB_RELEASE_FILE)
  return board


# A named tuple to store the probed component name and the error if any.
ProbedComponentResult = collections.namedtuple(
    'ProbedComponentResult', ['component_name', 'probed_values', 'error'])

UNPROBEABLE_COMPONENT_ERROR = lambda comp_cls: (
    'Component class %r is unprobeable' % comp_cls)
MISSING_COMPONENT_ERROR = lambda comp_cls: 'Missing %r component' % comp_cls
AMBIGUOUS_COMPONENT_ERROR = lambda comp_cls, probed_value, comp_names: (
    'Ambiguous probe values %s of %r component. Possible components are: %r' %
    (pprint.pformat(probed_value, indent=2), comp_cls, sorted(comp_names)))
INVALID_COMPONENT_ERROR = lambda comp_cls, probed_value: (
    'Invalid %r component found with probe result %s '
    '(no matching name in the component DB)' % (
        comp_cls, pprint.pformat(probed_value, indent=2)))
UNSUPPORTED_COMPONENT_ERROR = lambda comp_cls, comp_name, comp_status: (
    'Component %r of %r is %s' % (comp_name, comp_cls, comp_status))


class HWIDException(Exception):
  pass


class HWID(object):
  """A class that holds all the context of a HWID.

  It verifies the correctness of the HWID when a new HWID object is created.
  This class is mainly for internal use. User should not create a HWID object
  directly with the constructor.

  With bom (obatined from hardware prober) and board-specific component
  database, HWID encoder can derive binary_string and encoded_string.
  Reversely, with encoded_string and board-specific component database, HWID
  decoder can derive binary_string and bom.

  Attributes:
    database: A board-specific Database object.
    binary_string: A binary string. Ex: "0000010010..." It is used for fast
        component lookups as each component is represented by one or multiple
        bits at fixed positions.
    encoded_string: An encoded string with board name and checksum. For example:
        "CHROMEBOOK ASDF-2345", where CHROMEBOOK is the board name and 45 is the
        checksum. Compare to binary_string, it is human-trackable.
    bom: A BOM object.
    skip_check: Skips HWID self verification. This is needed when we want to
        create a HWID object skeleton for further processing, e.g. a skeleton
        HWID object to pass to rule evaluation to generate the final HWID.
        Defaults to False.

  Raises:
    HWIDException if an invalid arg is found.
  """
  HEADER_BITS = 5
  COMPONENT_STATUS = utils.Enum(['supported', 'deprecated', 'unsupported'])

  def __init__(self, database, binary_string, encoded_string, bom,
               skip_check=False):
    self.database = database
    self.binary_string = binary_string
    self.encoded_string = encoded_string
    self.bom = bom
    if not skip_check:
      self.VerifySelf()

  def VerifySelf(self):
    """Verifies the HWID object itself.

    Raises:
      HWIDException on verification error.
    """
    # pylint: disable=W0404
    from cros.factory.hwid.decoder import BinaryStringToBOM
    from cros.factory.hwid.decoder import EncodedStringToBinaryString
    self.database.VerifyBOM(self.bom)
    self.database.VerifyBinaryString(self.binary_string)
    self.database.VerifyEncodedString(self.encoded_string)
    if (EncodedStringToBinaryString(self.database, self.encoded_string) !=
        self.binary_string):
      raise HWIDException(
          'Encoded string %s does not decode to binary string %r' %
          (self.encoded_string, self.binary_string))
    if BinaryStringToBOM(self.database, self.binary_string) != self.bom:
      def GetComponentsDifferences(decoded, target):
        results = []
        for comp_cls in set(
            decoded.components.keys() + target.components.keys()):
          if comp_cls not in decoded.components:
            results.append('Decoded: does not exist. BOM: %r' %
                target.components[comp_cls])
          elif comp_cls not in target.components:
            results.append('Decoded: %r. BOM: does not exist.' %
                decoded.components[comp_cls])
          elif decoded.components[comp_cls] != target.components[comp_cls]:
            results.append('Decoded: %r != BOM: %r' %
                (decoded.components[comp_cls], target.components[comp_cls]))
        return results
      raise HWIDException(
          'Binary string %r does not decode to BOM. Differences: %r' %
          (self.binary_string, GetComponentsDifferences(
              self.bom, BinaryStringToBOM(self.database, self.binary_string))))
    # No exception. Everything is good!

  def VerifyComponentStatus(self, rma_mode=False):
    """Verifies the status of all components.

    Accepts all 'supported' components, rejects all 'unsupported' components,
    and accepts/rejects 'deprecated' components if rma_mode is True/False.

    Args:
      rma_mode: Whether to verify components status in RMA mode.

    Raises:
      HWIDException is verification fails.
    """
    for comp_cls, comps in self.bom.components.iteritems():
      for comp in comps:
        comp_name = comp.component_name
        if not comp_name:
          continue

        status = self.database.components.GetComponentStatus(
            comp_cls, comp_name)
        if status == HWID.COMPONENT_STATUS.supported:
          continue
        elif status == HWID.COMPONENT_STATUS.unsupported:
          raise HWIDException('Found unsupported component of %r: %r' %
                              (comp_cls, comp_name))
        elif status == HWID.COMPONENT_STATUS.deprecated:
          if not rma_mode:
            raise HWIDException(
                'Not in RMA mode. Found deprecated component of %r: %r' %
                (comp_cls, comp_name))

  def VerifyProbeResult(self, probe_result):
    """Verifies that the probe result matches the settings encoded in the HWID
    object.

    Args:
      probe_result: A YAML string of the probe result, which is usually the
          output of the probe command.

    Raises:
      HWIDException on verification error.
    """
    self.database.VerifyComponents(probe_result)
    probed_bom = self.database.ProbeResultToBOM(probe_result)
    def PackProbedValues(bom, comp_cls):
      results = []
      for e in bom.components[comp_cls]:
        if e.probed_values is None:
          continue
        matched_component = self.database.components.MatchComponentsFromValues(
            comp_cls, e.probed_values)
        if matched_component:
          results.extend(matched_component.keys())
      return results
    for comp_cls in self.database.components.GetRequiredComponents():
      if comp_cls not in self.database.components.probeable:
        continue
      probed_components = common.MakeSet(PackProbedValues(probed_bom, comp_cls))
      expected_components = common.MakeSet(PackProbedValues(self.bom, comp_cls))
      extra_components = probed_components - expected_components
      missing_components = expected_components - probed_components
      if extra_components or missing_components:
        err_msg = 'Component class %r' % comp_cls
        if extra_components:
          err_msg += ' has extra components: %r' % sorted(extra_components)
        if missing_components:
          if extra_components:
            err_msg += ' and'
          err_msg += ' is missing components: %r' % sorted(missing_components)
        err_msg += '. Expected components are: %r' % (
            sorted(expected_components) if expected_components else None)
        raise HWIDException(err_msg)

  def GetLabels(self):
    """Gets from the database the labels of all the components encoded in this
    HWID object.

    Returns:
      A dict of the form:
      {
        'component_class_1': {
          'component_name_1': {
            'label_key_1': 'LABEL_1_VALUE',
            'label_key_2': 'LABEL_2_VALUE',
            ...
          },
          ...
        },
        'component_class_2': {
          'component_name_2': None  # No labels were defined on this component.
        },
        ...
      }
    """
    results = collections.defaultdict(dict)
    for comp_cls, comp_data in self.bom.components.iteritems():
      for comp_value in comp_data:
        if comp_value.component_name:
          db_comp_attrs = self.database.components.GetComponentAttributes(
              comp_cls, comp_value.component_name)
          results[comp_cls][comp_value.component_name] = copy.deepcopy(
              db_comp_attrs.get('labels', None))
    return results


class BOM(object):
  """A class that holds all the information regarding a BOM.

  Attributes:
    board: A string of board name.
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
                 schema.Optional(schema.Dict('probed_values',
                               key_type=schema.Scalar('key', str),
                               value_type=schema.AnyOf([
                                   schema.Scalar('value', str),
                                   schema.Scalar('value', rule.Value)]))),
                 schema.Optional(schema.Scalar('error', str))])))

  def __init__(self, board, encoding_pattern_index, image_id,
               components, encoded_fields):
    self.board = board
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
