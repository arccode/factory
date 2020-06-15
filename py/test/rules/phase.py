# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import functools
import logging
import os

from cros.factory.test.env import paths
from cros.factory.utils import file_utils


PHASE_NAMES = ['PROTO', 'EVT', 'DVT', 'PVT_DOGFOOD', 'PVT']
PHASE_NAME_TO_INDEX_MAP = dict(
    (name, index)
    for (index, name) in enumerate(PHASE_NAMES))


# Current phase; unknown at first and read lazily from
# /var/factory/state/PHASE when required.
_current_phase = None


class PhaseAssertionError(Exception):
  pass


@functools.total_ordering
class Phase:
  """Object representing a build phase.

  Valid phases are PROTO, EVT, DVT, PVT_DOGFOOD, and PVT.

  - PROTO = prototype build (most forgiving; can be used for testing)
  - EVT = first build with plastics
  - DVT = second build with plastics
  - PVT_DOGFOOD = production of salable units, except that write protection
    may be disabled.  These are suitable for internal "dogfood" testing
    (http://goo.gl/iU8vlW), but non-write-protected devices may not actually
    be sold.
  - PVT = production of salable units
  """

  def __init__(self, name):
    """Constructor.

    Args:
      name: The name of a valid build phase.  Alternatively this may be another
          Phase object, in which case this acts as a copy constructor.
    """
    # If name is actually an already-constructed Phase option,
    # just create a copy of it.
    if isinstance(name, Phase):
      name = name.name

    self.name = name
    self.index = PHASE_NAME_TO_INDEX_MAP.get(self.name)
    if self.index is None:
      raise ValueError('%r is not a valid phase name (valid names are [%s])' %
                       (name, ','.join(PHASE_NAMES)))

  def __str__(self):
    return self.name

  def __repr__(self):
    return 'Phase(%s)' % self.name

  def __eq__(self, other):
    return self.index == other.index

  def __ne__(self, other):
    return self.index != other.index

  def __lt__(self, other):
    return self.index < other.index

  def __hash__(self):
    return self.index


_state_root_for_testing = None


def GetPhaseStatePath():
  """Returns the path used to save the current phase."""
  return os.path.join((_state_root_for_testing or paths.DATA_STATE_DIR),
                      'PHASE')


def GetPhase():
  """Gets the current state from /var/factory/state.

  If no state has been set, a warning is logged and
  the strictest state ('PVT') is used.
  """
  global _current_phase  # pylint: disable=global-statement
  if _current_phase:
    return _current_phase

  strictest_phase = Phase(PHASE_NAMES[-1])

  # There is a potential for a harmless race condition where we will
  # read the phase twice if GetPhase() is called twice in separate
  # threads.  No big deal.
  path = GetPhaseStatePath()
  try:
    with open(path, 'r') as f:
      phase = Phase(f.read())

    if (phase != strictest_phase and
        os.system('crossystem phase_enforcement?1 >/dev/null 2>&1') == 0):
      logging.warning('Hardware phase_enforcement activated, '
                      'enforce phase %s as %s.', phase, strictest_phase)
      phase = strictest_phase

  except IOError:
    phase = strictest_phase
    logging.warning('Unable to read %s; using strictest phase (%s)', path,
                    phase)

  _current_phase = phase
  return phase


def AssertStartingAtPhase(starting_at_phase, condition, message):
  """Assert a condition at or after a given phase.

  Args:
    starting_at_phase: The phase at which to start checking this condition.
        This may either be a string or a Phase object.
    condition: A condition to evaluate.  This may be a callable (in which
        case it is called if we're at/after the given phase), or a simple
        Boolean value.
    message: An error to include in exceptions if the check fails.  For example,
        "Expected write protection to be enabled".

  Raises:
    PhaseAssertionError: If the assertion fails.  For instance, if the ``phase``
        argument is set to ``phase.EVT``, we are currently in the DVT phase, and
        the condition evaluates to false, then we will raise an exception with
        the error message::

          Assertion starting at EVT failed (currently in DVT): Expected write
          protection to be enabled
  """
  # Coerce to an object in case a string was provided.
  starting_at_phase = Phase(starting_at_phase)

  current_phase = GetPhase()
  if starting_at_phase > current_phase:
    # We're not at phase yet; waive the check.
    return

  # Call the condition if it's callable (e.g., caller wants to defer an
  # expensive computation if the phase has not yet been reached)
  if callable(condition):
    condition = condition()

  if not condition:
    raise PhaseAssertionError(
        'Assertion starting at %s failed (currently in %s): %s' % (
            starting_at_phase, current_phase, message))


def SetPersistentPhase(phase):
  """Sets the current phase in /var/factory/state.

  This should be invoked only by Goofy.

  Args:
    phase: A Phase object, the name of a phase, or None.
        If None, the file containing the phase is deleted.
  """
  global _current_phase  # pylint: disable=global-statement

  path = GetPhaseStatePath()

  if phase:
    phase = Phase(phase)  # Coerce to Phase object
    logging.info('Setting phase to %s in %s', phase, path)
    file_utils.TryMakeDirs(os.path.dirname(path))
    with open(path, 'w') as f:
      f.write(phase.name)
  else:
    logging.info('Deleting phase in %s', path)
    file_utils.TryUnlink(path)

  _current_phase = phase


def OverridePhase(phase):
  """Override current phase for this process.

  This function overrides current phase of this python process. The phase is not
  saved persistently.

  Args:
    phase: A Phase object, the name of a phase, or None.
        If None, the phase is reset, next GetPhase() call will read from
        persistent state again.
  """
  global _current_phase  # pylint: disable=global-statement
  if phase:
    _current_phase = Phase(phase)  # Coerce to Phase object
  else:
    _current_phase = None


# Definitions for globals.  We could automatically do this based on
# PHASE_NAMES, but instead we define them manually to make lint happy.
PROTO = Phase('PROTO')
EVT = Phase('EVT')
DVT = Phase('DVT')
PVT_DOGFOOD = Phase('PVT_DOGFOOD')
PVT = Phase('PVT')
