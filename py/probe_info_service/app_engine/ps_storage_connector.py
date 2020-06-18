# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import abc
import logging
import typing

# pylint: disable=no-name-in-module,import-error
from google.cloud import datastore
# pylint: enable=no-name-in-module,import-error

from cros.factory.probe_info_service.app_engine import config
from cros.factory.utils import type_utils


class OverriddenProbeData:
  """Placeholder for an overridden probe statement and its metadata.

  Properties:
    is_tested: Whether the probe statement is tested on a real device.
    is_reviewed: Whether the probe statement is reviewed.
    probe_statement: A string payload of the probe statement data.
  """
  def __init__(self, is_tested: bool, is_reviewed: bool, probe_statement: str):
    self.is_tested = is_tested
    self.is_reviewed = is_reviewed
    self.probe_statement = probe_statement

  def __repr__(self):
    return self.__dict__.__repr__()


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
  def SetProbeStatementOverridden(
      self, qual_id, device_id, init_probe_statement) -> str:
    """Sets the probe statement of the qualification to manual maintained.

    For any unexpected case that makes the qualification need an specialized
    probe statement, the service stops treating generating the probe statement.
    Instead, the probe statement storage becomes the single source that the
    developer is expected to update the probe statement manually to the
    storage system directly.

    Args:
      qual_id: Numeric identity of the qualification.
      device_id: A non-empty string of the device name if this overridden
          is device-specific.
      init_probe_statement: A string of probe statement as an initial payload.

    Returns:
      A string of summary message to show to the user.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def MarkOverriddenProbeStatementTested(self, qual_id, device_id):
    """Mark the overridden probe statement for the qualification tested.

    Since the probe statement storage system itself is an interface for
    developers to upload changes and the test result, the test result of
    overridden probe statement is managed by the storage instead of the
    service's database system.

    Args:
      qual_id: Numeric identity of the qualification.
      device_id: A non-empty string of the device name if this overridden
          is device-specific.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def TryLoadOverriddenProbeData(
      self, qual_id, device_id) -> typing.Optional[OverriddenProbeData]:
    """Try to loads the overridden probe statement of a qualification.

    Args:
      qual_id: Numeric identity of the qualification.
      device_id: A non-empty string of the device name if this overridden
          is device-specific.

    Returns:
      `OverriddenProbeData` for both the metadata and the probe statement if
      it exists.  Otherwise `None` is returned.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def Clean(self):
    """Clean out all probe statements for testing purpose."""
    raise NotImplementedError


class _InMemoryProbeStatementStorageConnector(IProbeStatementStorageConnector):
  """An in-memory implementation for unittesting purpose."""

  def __init__(self):
    super(_InMemoryProbeStatementStorageConnector, self).__init__()
    self._qual_probe_statement = {}
    self._overridden_probe_data = {}

  def SaveQualProbeStatement(self, qual_id, probe_statement):
    assert qual_id not in self._overridden_probe_data
    self._qual_probe_statement[qual_id] = probe_statement

  def SetProbeStatementOverridden(
      self, qual_id, device_id, init_probe_statement):
    key = (qual_id, device_id)
    assert key not in self._overridden_probe_data
    self._overridden_probe_data[key] = OverriddenProbeData(
        False, False, init_probe_statement)
    return 'OK: qual=%r, device=%r.' % (qual_id, device_id)

  def MarkOverriddenProbeStatementTested(self, qual_id, device_id):
    key = (qual_id, device_id)
    assert key in self._overridden_probe_data
    self._overridden_probe_data[key].is_tested = True

  def UpdateOverriddenProbeData(self, qual_id, device_id, probe_data):
    """Force set the overridden probe statement for qualification."""
    key = (qual_id, device_id)
    if probe_data is None:
      del self._overridden_probe_data[key]
    else:
      self._overridden_probe_data[key] = probe_data

  def TryLoadOverriddenProbeData(self, qual_id, device_id):
    key = (qual_id, device_id)
    return self._overridden_probe_data.get(key, None)

  def Clean(self):
    self._qual_probe_statement = {}
    self._overridden_probe_data = {}


class _DataStoreProbeStatementStorageConnector(IProbeStatementStorageConnector):
  """A temporary implementation for the instance running on AppEngine.

  Before go/cros-probe-statement-storage is finalized, this implementation
  using `datastore` as the placeholder is in charge of managing overridden
  probe statements so that end-to-end tests can work.
  """

  _GENERATED_QUAL_PROBE_STATEMENT_KIND = 'generated_probe_statement'
  _OVERRIDDEN_PROBE_DATA_KIND = 'overridden_probe_data'
  _PROBE_STATEMENT_KEY = 'probe_statement'

  def __init__(self):
    super(_DataStoreProbeStatementStorageConnector, self).__init__()
    self._client = datastore.Client()

  def SaveQualProbeStatement(self, qual_id, probe_statement):
    self._SaveEntity([self._GENERATED_QUAL_PROBE_STATEMENT_KIND, qual_id],
                     {self._PROBE_STATEMENT_KEY: probe_statement})
    logging.debug('Update the generated probe statement for qual %r by %r.',
                  qual_id, probe_statement)

  def SetProbeStatementOverridden(
      self, qual_id, device_id, init_probe_statement):
    data_instance = OverriddenProbeData(False, False, init_probe_statement)
    entity_path = self._GetOverriddenProbeDataPath(qual_id, device_id)
    self._SaveEntity(entity_path, data_instance.__dict__)
    logging.debug('Update the overridden probe statement for qual %r %s by %r.',
                  qual_id, '' if not device_id else 'on ' + device_id,
                  data_instance)
    return 'OK: entity path: %r' % (entity_path,)

  def MarkOverriddenProbeStatementTested(self, qual_id, device_id):
    entity_path = self._GetOverriddenProbeDataPath(qual_id, device_id)
    data_instance = OverriddenProbeData(**self._LoadEntity(entity_path))
    data_instance.is_tested = True
    self._SaveEntity(entity_path, data_instance.__dict__)

  def TryLoadOverriddenProbeData(self, qual_id, device_id):
    entity_path = self._GetOverriddenProbeDataPath(qual_id, device_id)
    try:
      db_data = self._LoadEntity(entity_path)
    except KeyError:
      return None
    return OverriddenProbeData(**db_data)

  def Clean(self):
    raise NotImplementedError

  def _GetOverriddenProbeDataPath(self, qual_id, device_id):
    name = str(qual_id) if not device_id else '%s-%s' % (qual_id, device_id)
    return [self._OVERRIDDEN_PROBE_DATA_KIND, name]

  def _LoadEntity(self, path_args):
    key = self._client.key(*path_args)
    data = self._client.get(key)
    if data is None:
      raise KeyError('path %r is not found in the datastore' % (path_args,))
    return data

  def _SaveEntity(self, path_args, data):
    key = self._client.key(*path_args)
    entity = datastore.Entity(key)
    entity.update(data)
    self._client.put(entity)


@type_utils.CachedGetter
def GetProbeStatementStorageConnector():
  env_type = config.Config().env_type
  if env_type == config.EnvType.LOCAL:
    return _InMemoryProbeStatementStorageConnector()
  return _DataStoreProbeStatementStorageConnector()
