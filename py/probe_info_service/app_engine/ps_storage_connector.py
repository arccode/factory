# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import abc


class OverriddenProbeData:
  """Placeholder for an overridden probe statement and its metadata.

  Properties:
    is_tested: Whether the probe statement is tested on a real device.
    is_reviewed: Whether the probe statement is reviewed.
    probe_statement: A string payload of the probe statement data.
  """
  def __init__(self, is_tested, is_reviewed, probe_statement):
    self.is_tested = is_tested
    self.is_reviewed = is_reviewed
    self.probe_statement = probe_statement


class IProbeStatementStorageConnector(abc.ABC):
  """Interface for the connector of a probe statement storage."""

  @abc.abstractmethod
  def SaveQualProbeStatement(self, qual_id, probe_statement):
    """Save the auto-generated probe statement of the specific qualification.

    This method is expected to be called only when the probe statement is
    qualified, i.e. both tested and reviewed.

    Args:
      qual_id: Numeric identity of the qualification.
      probe_statement: A string of probe statement to be stored.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def SetQualProbeStatementOverridden(self, qual_id, init_probe_statement):
    """Sets the probe statement of the qualification to manual maintained.

    For any unexpected case that makes the qualification need an specialized
    probe statement, the service stops treating generating the probe statement.
    Instead, the probe statement storage becomes the single source that the
    developer is expected to update the probe statement manually to the
    storage system directly.

    Args:
      qual_id: Numeric identity of the qualification.
      init_probe_statement: A string of probe statement as an initial payload.

    Returns:
      A string of summary message to show to the user.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def MarkOverriddenQualProbeStatementTested(self, qual_id):
    """Mark the overridden probe statement for the qualification tested.

    Since the probe statement storage system itself is an interface for
    developers to upload changes and the test result, the test result of
    overridden probe statement is managed by the storage instead of the
    service's database system.

    Args:
      qual_id: Numeric identity of the qualification.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def LoadOverriddenQualProbeData(self, qual_id):
    """Loads the overridden probe statement of a qualification.

    Args:
      qual_id: Numeric identity of the qualification.

    Returns:
      `OverriddenProbeData` for both the metadata and the probe statement.
    """
    raise NotImplementedError


class InMemoryProbeStatementStorageConnector(IProbeStatementStorageConnector):
  """An in-memory implementation for unittesting purpose."""

  def __init__(self):
    super(InMemoryProbeStatementStorageConnector, self).__init__()
    self._qual_probe_statement = {}
    self._overridden_qual_probe_data = {}

  def SaveQualProbeStatement(self, qual_id, probe_statement):
    assert qual_id not in self._overridden_qual_probe_data
    self._qual_probe_statement[qual_id] = probe_statement

  def SetQualProbeStatementOverridden(self, qual_id, init_probe_statement):
    assert qual_id not in self._overridden_qual_probe_data
    self._qual_probe_statement.pop(qual_id, None)
    self._overridden_qual_probe_data[qual_id] = OverriddenProbeData(
        False, False, init_probe_statement)
    return 'OK: %r' % qual_id

  def MarkOverriddenQualProbeStatementTested(self, qual_id):
    assert qual_id not in self._qual_probe_statement
    self._overridden_qual_probe_data[qual_id].is_tested = True

  def UpdateOverriddenQualProbeData(self, qual_id, probe_data):
    """Force set the overridden probe statement for qualification."""
    self._overridden_qual_probe_data[qual_id] = probe_data

  def LoadOverriddenQualProbeData(self, qual_id):
    assert qual_id not in self._qual_probe_statement
    return self._overridden_qual_probe_data[qual_id]


_instance = None


def GetProbeStatementStorageConnector():
  global _instance  # pylint: disable=global-statement
  if _instance is None:
    _instance = InMemoryProbeStatementStorageConnector()
  return _instance
