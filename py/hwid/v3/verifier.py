# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module focus on verification process of a HWID bom.

A HWID identity being generated successfully doesn't mean the HWID identity
is valid.  We have to make sure many things such as:
  1. The components encoded in the HWID identity is actually installed on the
     device.
  2. The status of the components matches the requirement (for example,
     "supported" for PVT and later build, "unqualified" for early build).
  3. The rootkey is mp for PVT and later build.
"""

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.test.rules import phase


def VerifyComponentStatus(database, bom, mode, current_phase=None):
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
  for comp_cls, comps in bom.components.iteritems():
    for comp in comps:
      comp_name = comp.component_name
      if not comp_name:
        continue

      status = database.components.GetComponentStatus(comp_cls, comp_name)
      if status == common.COMPONENT_STATUS.supported:
        continue
      if status == common.COMPONENT_STATUS.unqualified:
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
      elif status == common.COMPONENT_STATUS.unsupported:
        raise HWIDException('Found unsupported component of %r: %r' %
                            (comp_cls, comp_name))
      elif status == common.COMPONENT_STATUS.deprecated:
        if mode != common.OPERATION_MODE.rma:
          raise HWIDException(
              'Not in RMA mode. Found deprecated component of %r: %r' %
              (comp_cls, comp_name))


_PRE_MP_KEY_NAME_PATTERN = re.compile('_pre_?mp')
_MP_KEY_NAME_PATTERN = re.compile('_mp[_0-9v]*?[_a-z]*$')

def _IsMPKeyName(name):
  """Returns True if the key name looks like MP (not pre-MP).

  An MP key name does not contain the strings "_premp" or "_premp", and
  ends in something like "_mp" or "_mp_v2" or "_mpv2".
  """
  return (_MP_KEY_NAME_PATTERN.search(name) and
          not _PRE_MP_KEY_NAME_PATTERN.search(name))

def VerifyPhase(database, bom, current_phase=None):
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
  image_name = database.image_id[bom.image_id]
  if not image_name.startswith(expected_image_name_prefix):
    raise HWIDException(
        'In %s phase, expected an image name beginning with '
        '%r (but got image ID %r)' %
        (current_phase, expected_image_name_prefix, image_name))

  # MP-key checking applies only in PVT and above
  if current_phase >= phase.PVT:
    if 'firmware_keys' in bom.components:
      key_types = ['firmware_keys']
    else:
      key_types = ['key_recovery', 'key_root']

    errors = []
    for key_type in key_types:
      if key_type not in bom.components:
        raise HWIDException(
            'Component %r is required but not found.' % (key_type,))
      name = bom.components[key_type][0].component_name
      if not _IsMPKeyName(name):
        errors.append('%s component name is %r' % (key_type, name))
    if errors:
      raise HWIDException('MP keys are required in %s, but %s' % (
          current_phase, ' and '.join(errors)))


def VerifyBOM(database, decoded_bom, probed_bom):
  """Verifies that the BOM object decoded from the HWID identity matches
  the one obtained by probing the device.

  This verification function makes sure the HWID identity is not encoded from
  a fake BOM object.

  Args:
    decoded_bom: The BOM object decoded from the the HWID identity.
    probed_bom: The BOM object generated from the probed results.

  Raises:
    HWIDException if the BOM objects mismatch.
  """
  # We only verify the components listed in the pattern.
  for comp_cls in database.GetActiveComponents(decoded_bom.image_id):
    if comp_cls not in probed_bom.components:
      raise HWIDException(
          'Component class %r is not found in probed BOM.' % comp_cls)

    decoded_components = set(
        [comp.component_name for comp in decoded_bom.components[comp_cls]])
    probed_components = set(
        [comp.component_name for comp in probed_bom.components[comp_cls]])

    err_msgs = []

    extra_components = decoded_components - probed_components
    if extra_components:
      err_msgs.append('has extra components: %r' % sorted(extra_components))

    missing_components = probed_components - decoded_components
    if missing_components:
      err_msgs.append('is missing components: %r' % sorted(missing_components))

    if err_msgs:
      raise HWIDException(
          'Component class %r ' % comp_cls + ' and '.join(err_msgs) +
          '.  Expected components are: %r' % sorted(probed_components))
