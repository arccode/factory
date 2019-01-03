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

import collections
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.test.rules import phase
from cros.factory.hwid.v3.configless_fields import ConfiglessFields


def VerifyComponentStatus(database, bom, mode, current_phase=None):
  """Verifies the status of all components.

  Accepts all 'supported' components, rejects all 'unsupported' components,
  accepts/rejects 'deprecated' components if operation mode is/is not
  rma and accepts 'unqualified' components if current phase is not
  PVT_DOGFOOD/PVT.

  Args:
    database: The Database object which records the status of each components.
    bom: The BOM object to be verified.
    mode: Either "normal" or "rma".
    current_phase: The current phase, for phase checks.  If None is
        specified, then phase.GetPhase() is used (this defaults to PVT
        if none is available).

  Raises:
    HWIDException if verification fails.
  """
  for comp_cls, comp_names in bom.components.iteritems():
    for comp_name in comp_names:
      status = database.GetComponents(comp_cls)[comp_name].status
      if status == common.COMPONENT_STATUS.supported:
        continue
      if status == common.COMPONENT_STATUS.unqualified:
        # Coerce current_phase to a Phase object, and use default phase
        # if unspecified.
        current_phase = (phase.Phase(current_phase) if current_phase
                         else phase.GetPhase())
        if current_phase == phase.PVT_DOGFOOD or current_phase == phase.PVT:
          raise common.HWIDException(
              'Found unqualified component of %r: %r in %r' %
              (comp_cls, comp_name, current_phase))
        else:
          continue
      elif status == common.COMPONENT_STATUS.unsupported:
        raise common.HWIDException('Found unsupported component of %r: %r' %
                                   (comp_cls, comp_name))
      elif status == common.COMPONENT_STATUS.deprecated:
        if mode != common.OPERATION_MODE.rma:
          raise common.HWIDException(
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
    database: The Database object which records image names.
    bom: The BOM object to be verified.
    current_phase: The current phase, for phase checks.  If None is
        specified, then phase.GetPhase() is used (this defaults to PVT
        if none is available).

  Raises:
    HWIDException if verification fails.
  """
  # Coerce current_phase to a Phase object, and use default phase
  # if unspecified.
  current_phase = (phase.Phase(current_phase) if current_phase
                   else phase.GetPhase())

  # Check image ID
  expected_image_name_prefix = ('PVT' if current_phase == phase.PVT_DOGFOOD
                                else current_phase.name)
  image_name = database.GetImageName(bom.image_id)
  if not image_name.startswith(expected_image_name_prefix):
    raise common.HWIDException(
        'In %s phase, expected an image name beginning with '
        '%r (but got image ID %r)' %
        (current_phase, expected_image_name_prefix, image_name))

  # MP-key checking applies only in PVT and above
  if current_phase >= phase.PVT:
    if 'firmware_keys' not in bom.components:
      raise common.HWIDException('firmware_keys is required but not found.')

    name = next(iter(bom.components['firmware_keys']))
    if not _IsMPKeyName(name):
      raise common.HWIDException(
          'MP keys are required in %r, but got %r' % (current_phase, name))


def VerifyBOM(database, decoded_bom, probed_bom):
  """Verifies that the BOM object decoded from the HWID identity matches
  the one obtained by probing the device.

  This verification function makes sure the HWID identity is not encoded from
  a fake BOM object.

  Args:
    database: The Database object which records what components to check.
    decoded_bom: The BOM object decoded from the the HWID identity.
    probed_bom: The BOM object generated from the probed results.

  Raises:
    HWIDException if the BOM objects mismatch.
  """
  def _GetExtraComponents(comps1, comps2):
    num_comps = collections.defaultdict(int)
    for comp in comps1:
      num_comps[comp] += 1

    for comp in comps2:
      if comp in num_comps:
        num_comps[comp] -= 1

    results = [[comp] * num_comp
               for comp, num_comp in num_comps.iteritems() if num_comp > 0]
    return sorted(sum(results, []))

  # We only verify the components listed in the pattern.
  for comp_cls in database.GetActiveComponentClasses(decoded_bom.image_id):
    if comp_cls not in probed_bom.components:
      raise common.HWIDException(
          'Component class %r is not found in probed BOM.' % comp_cls)

    err_msgs = []

    extra_components = _GetExtraComponents(decoded_bom.components[comp_cls],
                                           probed_bom.components[comp_cls])
    if extra_components:
      err_msgs.append('has extra components: %r' % extra_components)

    missing_components = _GetExtraComponents(probed_bom.components[comp_cls],
                                             decoded_bom.components[comp_cls])
    if missing_components:
      err_msgs.append('is missing components: %r' % missing_components)

    if err_msgs:
      raise common.HWIDException(
          'Component class %r ' % comp_cls + ' and '.join(err_msgs) +
          '.  Expected components are: %r' % probed_bom.components[comp_cls])


def VerifyConfigless(database, decoded_configless, bom, device_info):
  """Verifies that the configless dict decoded from the HWID identity matches
  the one obtained by probing the device.

  Args:
    database: The Database object which records what components to check.
    decoded_configless: The configless dict decoded from the the HWID identity.
    bom: The BOM object generated from the probed results.
    device_info: The device info object.

  Raises:
    HWIDException if the configless dict mismatch.
  """
  def _GetExtraComponents(comps1, comps2):
    return list(set(comps1.keys()) - set(comps2.keys()))

  if 'version' not in decoded_configless:
    raise common.HWIDException('Configless dict lacks version field.')

  encoded_configless = ConfiglessFields.Encode(database, bom, device_info,
                                               decoded_configless['version'])
  configless_fields = ConfiglessFields.Decode(encoded_configless)

  err_msgs = []
  extra_components = _GetExtraComponents(decoded_configless, configless_fields)
  if extra_components:
    err_msgs.append('has extra components: %r' % extra_components)

  missing_components = _GetExtraComponents(configless_fields,
                                           decoded_configless)
  if missing_components:
    err_msgs.append('is missing components: %r' % missing_components)

  if err_msgs:
    raise common.HWIDException('Configless dict ' + ' and '.join(err_msgs))

  for field in configless_fields:
    if configless_fields[field] != decoded_configless[field]:
      err_msgs.append('%r should be %r (got %r)' % (field,
                                                    configless_fields[field],
                                                    decoded_configless[field]))

  if err_msgs:
    raise common.HWIDException('Configless field ' + ', '.join(err_msgs))
