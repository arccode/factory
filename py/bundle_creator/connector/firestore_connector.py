# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import logging

# pylint: disable=no-name-in-module,import-error
from google.cloud import firestore
# pylint: enable=no-name-in-module,import-error


class FirestoreConnector:
  """ The connector for accessing the Cloud Firestore database."""

  COLLECTION_HAS_FIRMWARE_SETTINGS = 'has_firmware_settings'
  COLLECTION_USER_REQUESTS = 'user_requests'
  USER_REQUEST_STATUS_NOT_STARTED = 'NOT_STARTED'
  USER_REQUEST_STATUS_IN_PROGRESS = 'IN_PROGRESS'
  USER_REQUEST_STATUS_SUCCEEDED = 'SUCCEEDED'
  USER_REQUEST_STATUS_FAILED = 'FAILED'

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

  def CreateUserRequest(self, request):
    """Create a user request from the create bundle request.

    Args:
      request: A CreateBundleRpcRequest message.

    Returns:
      A hashed document id generated from the created document.
    """
    doc_value = {
        'email': request.email,
        'board': request.board,
        'project': request.project,
        'phase': request.phase,
        'toolkit_version': request.toolkit_version,
        'test_image_version': request.test_image_version,
        'release_image_version': request.release_image_version,
        'status': self.USER_REQUEST_STATUS_NOT_STARTED,
        'request_time': datetime.datetime.now(),
    }
    if request.HasField('firmware_source'):
      doc_value['firmware_source'] = request.firmware_source
    doc_ref = self._client.collection(self.COLLECTION_USER_REQUESTS).document()
    doc_ref.set(doc_value)
    return doc_ref.id

  def UpdateUserRequestStatus(self, doc_id, status):
    """Update `status` of the specific user request document.

    Args:
      doc_id: The document id of the document to be updated.
      status: The value used to update.
    """
    doc_ref = self._client.collection(
        self.COLLECTION_USER_REQUESTS).document(doc_id)
    doc_ref.update({'status': status})

  def UpdateUserRequestStartTime(self, doc_id):
    """Update `start_time` of the specific user request document.

    Args:
      doc_id: The document id of the document to be updated.
    """
    self.UpdateUserRequestWithCurrentTime(doc_id, 'start_time')

  def UpdateUserRequestEndTime(self, doc_id):
    """Update `end_time` of the specific user request document.

    Args:
      doc_id: The document id of the document to be updated.
    """
    self.UpdateUserRequestWithCurrentTime(doc_id, 'end_time')

  def UpdateUserRequestWithCurrentTime(self, doc_id, field_name):
    """Update the specific field of the user request with the current time.

    Args:
      doc_id: The document id of the document to be updated.
      field_name: The field name used to be updated with the current datetime.
    """
    doc_ref = self._client.collection(
        self.COLLECTION_USER_REQUESTS).document(doc_id)
    doc_ref.update({field_name: datetime.datetime.now()})

  def UpdateUserRequestErrorMessage(self, doc_id, error_msg):
    """Update an error message to the specific user request document.

    Args:
      doc_id: The document id of the document to be updated.
      error_msg: The string value used to update.
    """
    doc_ref = self._client.collection(
        self.COLLECTION_USER_REQUESTS).document(doc_id)
    doc_ref.update({'error_message': error_msg})

  def GetUserRequestsByEmail(self, email):
    """Returns user requests with the specific email.

    Args:
      email: The requestor's email.

    Returns:
      A list of dictionaries which represent the specific user requests in
      descending order of `request_time`.
    """
    col_ref = self._client.collection(self.COLLECTION_USER_REQUESTS)
    return [
        doc.to_dict() for doc in col_ref.where('email', '==', email).order_by(
            'request_time', direction=firestore.Query.DESCENDING).stream()
    ]
