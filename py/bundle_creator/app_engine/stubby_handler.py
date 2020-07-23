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

  @allowlist
  def CreateBundleAsync(self, request):
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        config.GCLOUD_PROJECT, config.PUBSUB_TOPIC)
    publisher.publish(topic_path, request.SerializeToString())
    return factorybundle_pb2.CreateBundleRpcResponse()

  @allowlist
  def GetBundleHistory(self, request):
    client = storage.Client(project=config.GCLOUD_PROJECT)
    bucket = client.bucket(config.BUNDLE_BUCKET)

    board_set = {}
    for blob in bucket.list_blobs():
      bundle = factorybundle_pb2.Bundle()
      bundle.path = blob.name
      bundle.board, bundle.project, bundle.filename = blob.name.split('/')
      bundle.created_timestamp_s = float(blob.metadata.get(
          'Time-Created', datetime.datetime.timestamp(blob.time_created)))
      # TODO(b/144397795): the unit of uploaded_timestamp_ms is microsecond, not
      #                    milisecond.
      bundle.uploaded_timestamp_ms = int(bundle.created_timestamp_s * (10 ** 6))
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
    response.bundles.sort(key=lambda b: b.uploaded_timestamp_ms, reverse=True)
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
