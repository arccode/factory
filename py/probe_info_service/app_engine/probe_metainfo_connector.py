# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=no-name-in-module,import-error
from google.cloud import datastore
# pylint: enable=no-name-in-module,import-error


class QualProbeMetaInfo:
  """Record class for the probe-related meta info of a qualification.

  Properties:
    is_overridden: A boolean indicating whether the probe statement of the
        target qualification is overridden or not.
    last_tested_probe_info_fp: A string of the fingerprint of the probe
        info that is known to be tested last.
    last_probe_info_fp_for_overridden: A string of the fingerprint of the probe
        info that turns out an evidence for probe statement overridden.
  """
  def __init__(self, is_overridden, last_tested_probe_info_fp,
               last_probe_info_fp_for_overridden):
    self.is_overridden = is_overridden
    self.last_tested_probe_info_fp = last_tested_probe_info_fp
    self.last_probe_info_fp_for_overridden = last_probe_info_fp_for_overridden


class ProbeMetaInfoConnector:
  _QUAL_PROBE_META_INFO_KIND = 'qual_meta_info'

  """A connector which manages IO of the DB for all probe metainfo."""
  def __init__(self):
    self._client = datastore.Client()

  def GetQualProbeMetaInfo(self, qual_id):
    """Retrieve the probe meta info of the specific qualification.

    Args:
      qual_id: The ID of the target qualification.

    Returns:
      An instance of `QualProbeMetaInfo`.
    """
    key = self._client.key(self._QUAL_PROBE_META_INFO_KIND, qual_id)
    db_data = (self._client.get(key) or
               {'is_overridden': False, 'last_tested_probe_info_fp': None,
                'last_probe_info_fp_for_overridden': None})
    return QualProbeMetaInfo(**db_data)

  def UpdateQualProbeMetaInfo(self, qual_id, qual_probe_meta_info):
    """Update the probe meta info of the specific qualification.

    Args:
      qual_id: The ID of the target qualification.
      qual_probe_meta_info: Instance of `QualProbeMetaInfo` containing the
          updated data.
    """
    key = self._client.key(self._QUAL_PROBE_META_INFO_KIND, qual_id)
    entity = datastore.Entity(key)
    entity.update(qual_probe_meta_info.__dict__)
    self._client.put(entity)

  def Clean(self):
    """Testing purpose.  Clean-out all the data."""
    q = self._client.query(kind=self._QUAL_PROBE_META_INFO_KIND)
    self._client.delete_multi([e.key for e in q.fetch()])


_probe_meta_info_connector = None


def GetProbeMetaInfoConnectorInstance():
  global _probe_meta_info_connector  # pylint: disable=global-statement
  if not _probe_meta_info_connector:
    _probe_meta_info_connector = ProbeMetaInfoConnector()
  return _probe_meta_info_connector
