# -*- coding: utf-8 -*-
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common classes for HWID v3 operation."""

import collections
import json
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.rules import phase
from cros.factory.utils import type_utils


PRE_MP_KEY_NAME_PATTERN = re.compile('_pre_?mp')
MP_KEY_NAME_PATTERN = re.compile('_mp[_0-9v]*?[_a-z]*$')


def IsMPKeyName(name):
  """Returns True if the key name looks like MP (not pre-MP).

  An MP key name does not contain the strings "_premp" or "_premp", and
  ends in something like "_mp" or "_mp_v2" or "_mpv2".
  """
  return (MP_KEY_NAME_PATTERN.search(name) and
          not PRE_MP_KEY_NAME_PATTERN.search(name))

# A named tuple to store the probed component name and the error if any.
ProbedComponentResult = collections.namedtuple(
    'ProbedComponentResult', ['component_name', 'probed_values', 'error'])

UNPROBEABLE_COMPONENT_ERROR = lambda comp_cls: (
    'Component class %r is unprobeable' % comp_cls)
MISSING_COMPONENT_ERROR = lambda comp_cls: 'Missing %r component' % comp_cls
AMBIGUOUS_COMPONENT_ERROR = lambda comp_cls, probed_value, comp_names: (
    'Ambiguous probe values %s of %r component. Possible components are: %r' %
    (json.dumps(probed_value, indent=2), comp_cls, sorted(comp_names)))
INVALID_COMPONENT_ERROR = lambda comp_cls, probed_value: (
    'Invalid %r component found with probe result %s '
    '(no matching name in the component DB)' % (
        comp_cls, json.dumps(probed_value, indent=2)))
UNSUPPORTED_COMPONENT_ERROR = lambda comp_cls, comp_name, comp_status: (
    'Component %r of %r is %s' % (comp_name, comp_cls, comp_status))


class HWIDException(Exception):
  """HWID-related exception."""
  pass


class HWID(object):
  """A class that holds all the context of a HWID.

  It verifies the correctness of the HWID when a new HWID object is created.
  This class is mainly for internal use. User should not create a HWID object
  directly with the constructor.

  With BOM (obtained from hardware prober) and project-specific component
  database, HWID encoder can derive binary_string and encoded_string.
  Reversely, with encoded_string and project-specific component database, HWID
  decoder can derive binary_string and bom. Therefore, we only keep the BOM
  object and calculate the binary_string and encoded_string. But we still keep
  the binary_string while the this object is decoded by the HWID string, because
  the binary string encoded by the later database might be changed.

  Since the HWID object might be skeleton for further processing, e.g. a
  skeleton HWID object to pass to rule evaluation, the bom might be invalid with
  the database. Therefore we generate HWID string (binary_string and
  encoded_string) lazily.

  Attributes:
    database: A project-specific Database object.
    bom: A BOM object.
    binary_string: A string only containing '0' or '1'. When the binary_string
        is needed, return it if it is matched to the BOM.
    encoded_string: The encoded HWID string.
    mode: The operation mode of the HWID object. 'normal' indicates the normal
        workflow where all checks applies and deprecated components are not
        allowed. 'rma' indicates the HWID is goning through RMA process and
        deprecated components are allowed to present. Defaults to 'normal'.
    skip_check: True to skip HWID verification checks. This is used when we want
        to create a HWID object skeleton for further processing, e.g. a skeleton
        HWID object to pass to rule evaluation to generate the final HWID.
        Defaults to False.

  Raises:
    HWIDException if an invalid arg is found.
  """
  HEADER_BITS = 5
  OPERATION_MODE = type_utils.Enum(['normal', 'rma', 'no_check'])
  COMPONENT_STATUS = type_utils.Enum(['supported', 'deprecated',
                                      'unsupported', 'unqualified'])
  ENCODING_SCHEME = type_utils.Enum(['base32', 'base8192'])

  def __init__(self, database, bom, identity=None,
               mode=OPERATION_MODE.normal, skip_check=False):
    self.database = database
    self.bom = bom
    if identity is not None and identity.binary_string[-1] != '1':
      raise HWIDException('The last bit of binary_string must be 1.')
    self._identity = identity
    if mode not in HWID.OPERATION_MODE:
      raise HWIDException('Invalid operation mode: %r. Mode must be one of: '
                          "'normal' or 'rma'" % mode)
    self.mode = mode
    if not skip_check:
      self.VerifySelf()

  def __eq__(self, other):
    """Define the equivalence of HWID.

    Two HWID are equivalent if the projects are the same, and the binary string
    is equivalent.
    """
    if not isinstance(other, HWID):
      return False
    if self.database.project != other.database.project:
      return False
    return HWID.IsEquivalentBinaryString(self.binary_string,
                                         other.binary_string)

  @staticmethod
  def IsEquivalentBinaryString(str_a, str_b):
    """Define the equivalence of binary string.

    Without the last stop bit, the common part of binary_string are the same,
    and the extra part of the binary string are all 0.
    For example:
      '01001' and '0100001' are equivalent.
    """
    assert str_a[-1] == '1' and str_b[-1] == '1', 'The last bit must be 1.'
    str_a = str_a[:-1]  # Remove the stop bit
    str_b = str_b[:-1]
    common_len = min(len(str_a), len(str_b))
    if str_a[:common_len] != str_b[:common_len]:
      return False
    if '1' in str_a[common_len:] or '1' in str_b[common_len:]:
      return False
    return True

  @property
  def binary_string(self):
    """A binary string generated by the database and the BOM.

    It is is represented by one or multiple bits at fixed positions. If the BOM
    and the self._binary_string is matched, then return it.
    """
    # pylint: disable=W0404
    from cros.factory.hwid.v3.encoder import BOMToBinaryString
    binary_string = BOMToBinaryString(self.database, self.bom)
    if (self._identity and
        HWID.IsEquivalentBinaryString(self._identity.binary_string,
                                      binary_string)):
      return self._identity.binary_string
    return binary_string

  @property
  def encoded_string(self):
    """An encoded string with project name and checksum.

    For example: "CHROMEBOOK ASDF-2345", where CHROMEBOOK is the project name
    and 45 is the checksum. Compare to binary_string, it is human-trackable.
    """
    # pylint: disable=W0404
    from cros.factory.hwid.v3.encoder import BinaryStringToEncodedString
    return BinaryStringToEncodedString(self.database, self.binary_string)

  def VerifySelf(self):
    """Verifies the HWID object itself.

    This method is to verify the BOM object matches the database and the
    generated HWID encoded string is valid. In HWID generation, the BOM object
    is invalid before evaluating the rule to add the unprobeable components and
    image ID. So this method should be called after that.

    Raises:
      HWIDException on verification error.
    """
    self.database.VerifyBOM(self.bom)
    self.database.VerifyEncodedString(self.encoded_string)

  def VerifyComponentStatus(self, current_phase=None):
    """Verifies the status of all components.

    Accepts all 'supported' components, rejects all 'unsupported' components,
    accepts/rejects 'deprecated' components if operation mode is/is not
    rma and accepts 'unqualified' components if current phase is not
    PVT_DOGFOOD/PVT.

    Args:
      current_phase: The current phase, for phase checks.  If None is
          specified, then phase.GetPhase() is used (this defaults to PVT
          if none is available).

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
        if status == HWID.COMPONENT_STATUS.unqualified:
          # Coerce current_phase to a Phase object, and use default phase
          # if unspecified.
          current_phase = (phase.Phase(current_phase) if current_phase
                           else phase.GetPhase())
          if current_phase == phase.PVT_DOGFOOD or current_phase == phase.PVT:
            raise HWIDException(
                'Found unqualified component of %r: %r in %r' %
                (comp_cls, comp_name, current_phase))
          else:
            continue
        elif status == HWID.COMPONENT_STATUS.unsupported:
          raise HWIDException('Found unsupported component of %r: %r' %
                              (comp_cls, comp_name))
        elif status == HWID.COMPONENT_STATUS.deprecated:
          if self.mode != HWID.OPERATION_MODE.rma:
            raise HWIDException(
                'Not in RMA mode. Found deprecated component of %r: %r' %
                (comp_cls, comp_name))

  def VerifyProbeResult(self, probe_result):
    """Verifies that the probe result matches the settings encoded in the HWID
    object.

    Args:
      probe_result: A JSON-serializable dict of the probe result, which is
          usually the output of the probe command.

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

    # We only verify the components listed in the pattern.
    for comp_cls in self.database.GetActiveComponents(self.bom.image_id):
      if comp_cls not in self.database.components.probeable:
        continue
      probed_components = type_utils.MakeSet(
          PackProbedValues(probed_bom, comp_cls))
      expected_components = type_utils.MakeSet(
          PackProbedValues(self.bom, comp_cls))
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

  def VerifyPhase(self, current_phase=None):
    """Enforces phase checks.

    - Starting in PVT_DOGFOOD, only an MP key (not a pre-MP key) may be used.
      The names of recovery and root keys in HWID files are required to end with
      "_mp" or "_mp_v[0-9]+", e.g., "_mp_v2".
    - The image ID must begin with the phase name (except that in PVT_DOGFOOD,
      the image ID must begin with 'PVT').

    Args:
      current_phase: The current phase, for phase checks.  If None is
          specified, then phase.GetPhase() is used (this defaults to PVT
          if none is available).
    """
    # Coerce current_phase to a Phase object, and use default phase
    # if unspecified.
    current_phase = (phase.Phase(current_phase) if current_phase
                     else phase.GetPhase())

    # Check image ID
    expected_image_name_prefix = ('PVT' if current_phase == phase.PVT_DOGFOOD
                                  else current_phase.name)
    image_name = self.database.image_id[self.bom.image_id]
    if not image_name.startswith(expected_image_name_prefix):
      raise HWIDException(
          'In %s phase, expected an image name beginning with '
          '%r (but %r has image ID %r)' %
          (current_phase, expected_image_name_prefix, self.encoded_string,
           image_name))

    # MP-key checking applies only in PVT and above
    if current_phase >= phase.PVT:
      if 'firmware_keys' in self.bom.components:
        key_types = ['firmware_keys']
      else:
        key_types = ['key_recovery', 'key_root']

      errors = []
      for key_type in key_types:
        name = self.bom.components[key_type][0].component_name
        if not IsMPKeyName(name):
          errors.append('%s component name is %r' % (key_type, name))
      if errors:
        raise HWIDException('MP keys are required in %s, but %s' % (
            current_phase, ' and '.join(errors)))
