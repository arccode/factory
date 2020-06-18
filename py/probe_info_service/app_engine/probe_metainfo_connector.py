# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import abc
import copy
import logging
import typing

# pylint: disable=no-name-in-module,import-error
from google.cloud import datastore
# pylint: enable=no-name-in-module,import-error

from cros.factory.probe_info_service.app_engine import config
from cros.factory.utils import type_utils


class QualProbeMetaInfo:
  """Record class for the probe-related meta info of a qualification.

  Note that named tuple is out of option for this class because the usage
  requires the caller to modify the attributes of the instance.

  Properties:
    last_tested_probe_info_fp: A string of the fingerprint of the probe
        info that is known to be tested last.
    last_probe_info_fp_for_overridden: A string of the fingerprint of the probe
        info that turns out an evidence for probe statement overridden.
  """
  def __init__(self, last_tested_probe_info_fp: typing.Optional[str],
               last_probe_info_fp_for_overridden: typing.Optional[str]):
    self.last_tested_probe_info_fp = last_tested_probe_info_fp
    self.last_probe_info_fp_for_overridden = last_probe_info_fp_for_overridden

  def __repr__(self):
    return self.__dict__.__repr__()


class IProbeMetaInfoConnector(abc.ABC):
  """Interface of a connector which manages all probe metainfo."""

  @abc.abstractmethod
  def GetQualProbeMetaInfo(self, qual_id) -> QualProbeMetaInfo:
    """Retrieve the probe meta info of the specific qualification.

    Args:
      qual_id: The ID of the target qualification.

    Returns:
      An instance of `QualProbeMetaInfo`.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def UpdateQualProbeMetaInfo(
      self, qual_id, qual_probe_meta_info: QualProbeMetaInfo):
    """Update the probe meta info of the specific qualification.

    Args:
      qual_id: The ID of the target qualification.
      qual_probe_meta_info: Instance of `QualProbeMetaInfo` containing the
          updated data.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def Clean(self):
    """Testing purpose.  Clean-out all the data."""
    raise NotImplementedError


class _DataStoreProbeMetaInfoConnector(IProbeMetaInfoConnector):
  """The connector which stores the probe metainfo in datastore."""

  _QUAL_PROBE_META_INFO_KIND = 'qual_meta_info'

  def __init__(self):
    self._client = datastore.Client()

  def GetQualProbeMetaInfo(self, qual_id) -> QualProbeMetaInfo:
    key = self._client.key(self._QUAL_PROBE_META_INFO_KIND, qual_id)
    db_data = (self._client.get(key) or
               {'last_tested_probe_info_fp': None,
                'last_probe_info_fp_for_overridden': None})
    return QualProbeMetaInfo(**db_data)

  def UpdateQualProbeMetaInfo(
      self, qual_id, qual_probe_meta_info: QualProbeMetaInfo):
    key = self._client.key(self._QUAL_PROBE_META_INFO_KIND, qual_id)
    entity = datastore.Entity(key)
    entity.update(qual_probe_meta_info.__dict__)
    self._client.put(entity)
    logging.debug('Update the probe metainfo of qual %r by %r.', qual_id,
                  qual_probe_meta_info)

  def Clean(self):
    env_type = config.Config().env_type
    if env_type == config.EnvType.PROD:
      raise RuntimeError('cleaning up datastore data for %r in %r runtime '
                         'environment is forbidden' %
                         (self._QUAL_PROBE_META_INFO_KIND, env_type))
    q = self._client.query(kind=self._QUAL_PROBE_META_INFO_KIND)
    self._client.delete_multi([e.key for e in q.fetch()])


class _InMemoryProbeMetaInfoConnector(IProbeMetaInfoConnector):
  def __init__(self):
    self._qual_probe_meta_infos = {}

  def GetQualProbeMetaInfo(self, qual_id) -> QualProbeMetaInfo:
    ret = copy.deepcopy(self._qual_probe_meta_infos.setdefault(
        qual_id, QualProbeMetaInfo(None, None)))
    logging.info('Fetch the probe metainfo of qual %r, got %r.', qual_id, ret)
    return ret

  def UpdateQualProbeMetaInfo(
      self, qual_id, qual_probe_meta_info: QualProbeMetaInfo):
    self._qual_probe_meta_infos[qual_id] = copy.deepcopy(qual_probe_meta_info)
    logging.info('Update the probe metainfo of qual %r by %r.', qual_id,
                 qual_probe_meta_info)

  def Clean(self):
    self._qual_probe_meta_infos = {}


@type_utils.CachedGetter
def GetProbeMetaInfoConnectorInstance() -> IProbeMetaInfoConnector:
  env_type = config.Config().env_type
  if env_type == config.EnvType.LOCAL:
    return _InMemoryProbeMetaInfoConnector()
  return _DataStoreProbeMetaInfoConnector()
