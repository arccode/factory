#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from collections import namedtuple

import factory_common  # pylint: disable=W0611
from cros.factory.hwdb import hwid_tool
from cros.factory.gooftool.probe import Probe


# A named tuple to store the probed component name and the error if any.
ProbedComponentResult = namedtuple('VerifyComponentResult',
                                  ['component_name', 'probed_string', 'error'])

class Gooftool(object):
  '''A class to perform hardware probing and verification and to implement
  Google required tests.
  '''
  # TODO(andycheng): refactor all other functions in gooftool.py to this.

  def __init__(self, probe=None, component_db=None):
    '''Constructor.

    Args:
      probe: The probe to use for detecting installed components. If not
        specified, cros.factory.gooftool.probe.Probe is used.

      component_db: The component db to use for both component names and
        component classes lookup. If not specified, the component_db under
        hwid_tool.DEFAULT_HWID_DATA_PATH is used.
    '''
    self._component_db = (
        component_db or
        hwid_tool.HardwareDb(hwid_tool.DEFAULT_HWID_DATA_PATH).comp_db)
    self._probe = probe or Probe

  def VerifyComponents(self, component_list):
    '''Verifies the given component list against the component db to ensure
    the installed components are correct.

    Args:
      component_list: A list of components to verify.
        (e.g., ['camera', 'cpu'])

    Returns:
      A dict from component class to a list of one or more
      ProbedComponentResult tuples.
      {component class: [ProbedComponentResult(
          component_name,  # The component name if found in the db, else None.
          probed_string,   # The actual probed string. None if probing failed.
          error)]}         # The error message if there is one.
    '''
    probeable_classes = self._component_db.probeable_components.keys()
    if not component_list:
      raise ValueError("No component classes specified;\n" +
                       "Possible choices: %s" % probeable_classes)

    unknown_class = [component_class for component_class in component_list
                     if component_class not in probeable_classes]
    if unknown_class:
      raise ValueError(("Invalid component classes specified: %s\n" +
                        "Possible choices: %s") %
                        (unknown_class, probeable_classes))

    probe_results = self._probe(
        target_comp_classes=component_list,
        probe_volatile=False, probe_initial_config=False)
    result = {}
    for comp_class in sorted(component_list):
      probe_vals = probe_results.found_probe_value_map.get(comp_class, None)

      if probe_vals is not None:
        if isinstance(probe_vals, str):
          # Force cast probe_val to be a list so it is easier to process later
          probe_vals = [probe_vals]

        result_tuples = []
        for val in probe_vals:
          comp_name = self._component_db.result_name_map.get(val, None)
          if comp_name is not None:
            result_tuples.append(ProbedComponentResult(comp_name, val, None))
          else:
            result_tuples.append(ProbedComponentResult(None, val, (
                'unsupported %r component found with probe result'
                ' %r (no matching name in the component DB)' %
                (comp_class, val))))
        result[comp_class] = result_tuples
      else:
        result[comp_class] = [ProbedComponentResult(None, None, (
            'missing %r component' % comp_class))]

    return result

