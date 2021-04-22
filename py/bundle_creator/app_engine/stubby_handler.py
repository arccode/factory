# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import flask

# pylint: disable=import-error,no-name-in-module,wrong-import-order
from google.cloud import pubsub_v1
from google.cloud import storage
# pylint: enable=import-error,no-name-in-module,wrong-import-order

from cros.factory.bundle_creator.app_engine import config
from cros.factory.bundle_creator.app_engine import factorybundle_pb2  # pylint: disable=no-name-in-module
from cros.factory.bundle_creator.app_engine import protorpc_utils
from cros.factory.bundle_creator.connector import firestore_connector


class AllowlistException(Exception):
  pass


def allowlist(function):
  def function_wrapper(*args, **kwargs):
    loas_peer_username = flask.request.headers.get(
        'X-Appengine-Loas-Peer-Username')
    if loas_peer_username not in config.ALLOWED_LOAS_PEER_USERNAMES:
      raise AllowlistException(
          'LOAS_PEER_USERNAME {} is not allowed'.format(loas_peer_username))
    return function(*args, **kwargs)
  return function_wrapper


class FactoryBundleService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = factorybundle_pb2.DESCRIPTOR.services_by_name[
      'FactoryBundleService']

  def __init__(self):
    self._firestore_connector = firestore_connector.FirestoreConnector(
        config.GCLOUD_PROJECT)

  @allowlist
  def CreateBundleAsync(self, request):
    message = factorybundle_pb2.CreateBundleMessage()
    message.doc_id = self._firestore_connector.CreateUserRequest(request)
    message.request.MergeFrom(request)
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        config.GCLOUD_PROJECT, config.PUBSUB_TOPIC)
    publisher.publish(topic_path, message.SerializeToString())

    return factorybundle_pb2.CreateBundleRpcResponse()

  @allowlist
  def GetBundleHistory(self, request):
    client = storage.Client(project=config.GCLOUD_PROJECT)
    bucket = client.bucket(config.BUNDLE_BUCKET)

    # Generate a board/device pair filtering set from the request.
    board_set = {}
    for blob in bucket.list_blobs():
      bundle = factorybundle_pb2.Bundle()
      bundle.path = blob.name
      bundle.board, bundle.project, bundle.filename = blob.name.split('/')
      bundle.created_timestamp_sec = float(
          blob.metadata.get('Time-Created',
                            datetime.datetime.timestamp(blob.time_created)))
      bundle.creator = blob.metadata.get('Bundle-Creator', '-')
      bundle.toolkit_version = blob.metadata.get('Tookit-Version', '-')
      bundle.test_image_version = blob.metadata.get('Test-Image-Version', '-')
      bundle.release_image_version = blob.metadata.get(
          'Release-Image-Version', '-')
      bundle.firmware_source = blob.metadata.get('Firmware-Source', '-')
      project_set = board_set.setdefault(bundle.board, {})
      project_set.setdefault(bundle.project, []).append(bundle)

    response = factorybundle_pb2.GetBundleHistoryRpcResponse()
    for board_projects in request.board_projects:
      for project in board_projects.projects:
        bundle_list = board_set.get(board_projects.board_name,
                                    {}).get(project.name, [])
        for bundle in bundle_list:
          response.bundles.append(bundle)
    response.bundles.sort(key=lambda b: b.created_timestamp_sec, reverse=True)
    return response

  @allowlist
  def DownloadBundle(self, request):
    client = storage.Client(project=config.GCLOUD_PROJECT)
    bucket = client.bucket(config.BUNDLE_BUCKET)

    blob = bucket.get_blob(request.path)
    blob.acl.reload()
    blob.acl.user(request.email).grant_read()
    blob.acl.save()

    response = factorybundle_pb2.DownloadBundleRpcResponse()
    response.download_link = 'https://storage.cloud.google.com/{}/{}'.format(
        config.BUNDLE_BUCKET, request.path)
    return response

  @allowlist
  def GetUserRequests(self, request):
    response = factorybundle_pb2.GetUserRequestsRpcResponse()

    board_set = {}
    for board in request.boards:
      project_set = board_set.setdefault(board.name, {})
      for project_name in board.project_names:
        project_set[project_name] = True

    snapshots = self._firestore_connector.GetUserRequestsByEmail(request.email)
    for snapshot in snapshots:
      board = snapshot.get('board', '-')
      project = snapshot.get('project', '-')
      if board not in board_set or project not in board_set[board]:
        continue

      user_request = factorybundle_pb2.GetUserRequestsRpcResponse.UserRequest()
      user_request.board = board
      user_request.project = project
      user_request.phase = snapshot.get('phase', '-')
      user_request.toolkit_version = snapshot.get('toolkit_version', '-')
      user_request.test_image_version = snapshot.get('test_image_version', '-')
      user_request.release_image_version = snapshot.get('release_image_version',
                                                        '-')
      user_request.firmware_source = snapshot.get('firmware_source', '-')
      user_request.email = snapshot.get('email', '-')
      user_request.status = snapshot.get('status', '-')
      # The returned fields with suffix `_time` are `DatetimeWithNanoseconds`
      # objects.
      if 'request_time' in snapshot:
        user_request.request_time_sec = datetime.datetime.timestamp(
            snapshot.get('request_time'))
      if 'start_time' in snapshot:
        user_request.start_time_sec = datetime.datetime.timestamp(
            snapshot.get('request_time'))
      if 'end_time' in snapshot:
        user_request.end_time_sec = datetime.datetime.timestamp(
            snapshot.get('end_time'))
      if 'error_message' in snapshot:
        user_request.error_message = snapshot.get('error_message')

      response.user_requests.append(user_request)
      if len(response.user_requests) >= 10:
        # Only response the latest 10 requests.
        break

    return response
