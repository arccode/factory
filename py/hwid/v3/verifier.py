# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.common import HWIDException
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


def VerifyBOM(database, bom, bom2):
  """Verifies that the BOM object matches the settings encoded in the HWID
  object.

  Args:
    bom: An instance of BOM to be verified.

  Raises:
    HWIDException on verification error.
  """
  VerifyComponents(database, bom2)

  def PackProbedValues(bom, comp_cls):
    results = []
    for e in bom.components[comp_cls]:
      if e.probed_values is None:
        continue
      matched_component = database.components.MatchComponentsFromValues(
          comp_cls, e.probed_values)
      if matched_component:
        results.extend(matched_component.keys())
    return results

  # We only verify the components listed in the pattern.
  for comp_cls in database.GetActiveComponents(bom.image_id):
    if comp_cls not in database.components.probeable:
      continue
    probed_components = type_utils.MakeSet(PackProbedValues(bom2, comp_cls))
    expected_components = type_utils.MakeSet(PackProbedValues(bom, comp_cls))
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
      name = bom.components[key_type][0].component_name
      if not IsMPKeyName(name):
        errors.append('%s component name is %r' % (key_type, name))
    if errors:
      raise HWIDException('MP keys are required in %s, but %s' % (
          current_phase, ' and '.join(errors)))


def VerifyComponents(database, bom, comp_list=None):
  """Given a list of component classes, verify that the probed components of
  all the component classes in the list are valid components in the database.

  Args:
    bom: A BOM object contains a list of components.
    comp_list: An optional list of component class to be verified. Defaults to
        None, which will then verify all the probeable components defined in
        the database.

  Returns:
    A dict from component class to a list of one or more
    ProbedComponentResult tuples.
    {component class: [ProbedComponentResult(
        component_name,  # The component name if found in the db, else None.
        probed_values,   # The actual probed string. None if probing failed.
        error)]}         # The error message if there is one; else None.
  """
  if not comp_list:
    comp_list = sorted(database.components.probeable)
  if not isinstance(comp_list, list):
    raise HWIDException('Argument comp_list should be a list')
  invalid_cls = set(comp_list) - set(database.components.probeable)
  if invalid_cls:
    raise HWIDException(
        '%r do not have probe values and cannot be verified' %
        sorted(invalid_cls))
  return dict((comp_cls, bom.components[comp_cls]) for comp_cls in comp_list)
