# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

# pylint: disable=no-name-in-module,import-error
from google.cloud import firestore
# pylint: enable=no-name-in-module,import-error


class FirestoreConnector:
  """ The connector for accessing the Cloud Firestore database."""

  COLLECTION_HAS_FIRMWARE_SETTINGS = 'has_firmware_settings'

  def __init__(self, cloud_project_id):
    """Initialize the firestore client by a cloud project id.

    Args:
      cloud_project_id: A cloud project id.
    """
    self._client = firestore.Client(project=cloud_project_id)

  def GetHasFirmwareSettingByProject(self, project):
    """Get the has_firmware setting by a project name.

    Args:
      project: The project name as the document id.

    Returns:
      An array contains the firmware names if it exists.  Otherwise `None` is
      returned.
    """
    logger = logging.getLogger('firestore_connector.get')
    doc = self._client.collection(
        self.COLLECTION_HAS_FIRMWARE_SETTINGS).document(project).get()
    if doc.exists:
      try:
        return doc.get('has_firmware')
      except KeyError:
        logger.info(
            'No `has_firmware` attribute found in the existing document.')
    return None
