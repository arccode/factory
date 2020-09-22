# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import logging
import time

from google.cloud import pubsub_v1  # pylint: disable=no-name-in-module,import-error
from googleapiclient import discovery  # pylint: disable=import-error

from cros.factory.bundle_creator.connector import firestore_connector
from cros.factory.bundle_creator.docker import config
from cros.factory.bundle_creator.docker import factorybundle_pb2  # pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import util


RESPONSE_CALLBACK = '/_ah/stubby/FactoryBundleService.ResponseCallback'
ACK_DEADLINE = 600


def ResponseResult(tasks, response_proto):
  tasks.create(
      parent=config.RESPONSE_QUEUE,
      body={
          'task': {
              'app_engine_http_request': {
                  'http_method': 'POST',
                  'app_engine_routing': {
                      'service': 'cloud-mail',
                  },
                  'relative_uri': RESPONSE_CALLBACK,
                  'body': base64.b64encode(
                      response_proto.SerializeToString()).decode('utf-8'),
              },
          },
      }).execute()


def PullTask():
  logger = logging.getLogger('worker.pull_task')
  cloudtasks = discovery.build('cloudtasks', 'v2beta3', cache_discovery=False)
  tasks = cloudtasks.projects().locations().queues().tasks()
  subscriber = pubsub_v1.SubscriberClient()
  subscription_path = subscriber.subscription_path(
      config.GCLOUD_PROJECT, config.PUBSUB_SUBSCRIPTION)
  firestore_conn = firestore_connector.FirestoreConnector(config.GCLOUD_PROJECT)
  message_proto = None
  try:
    response = subscriber.pull(subscription_path, max_messages=1)
    if response and response.received_messages:
      received_message = response.received_messages[0]
      subscriber.acknowledge(subscription_path, [received_message.ack_id])
      message_proto = factorybundle_pb2.CreateBundleMessage.FromString(
          received_message.message.data)

      firestore_conn.UpdateUserRequestStatus(
          message_proto.doc_id, firestore_conn.USER_REQUEST_STATUS_IN_PROGRESS)
      firestore_conn.UpdateUserRequestStartTime(message_proto.doc_id)

      gs_path = util.CreateBundle(message_proto.request)

      firestore_conn.UpdateUserRequestStatus(
          message_proto.doc_id, firestore_conn.USER_REQUEST_STATUS_SUCCEEDED)
      firestore_conn.UpdateUserRequestEndTime(message_proto.doc_id)

      response_proto = factorybundle_pb2.WorkerResult()
      response_proto.status = factorybundle_pb2.WorkerResult.NO_ERROR
      response_proto.original_request.MergeFrom(message_proto.request)
      response_proto.gs_path = gs_path
      ResponseResult(tasks, response_proto)
  except util.CreateBundleException as e:
    logger.error(e)

    firestore_conn.UpdateUserRequestStatus(
        message_proto.doc_id, firestore_conn.USER_REQUEST_STATUS_FAILED)
    firestore_conn.UpdateUserRequestEndTime(message_proto.doc_id)
    firestore_conn.UpdateUserRequestErrorMessage(message_proto.doc_id, str(e))

    response_proto = factorybundle_pb2.WorkerResult()
    response_proto.status = factorybundle_pb2.WorkerResult.FAILED
    response_proto.original_request.MergeFrom(message_proto.request)
    response_proto.error_message = str(e)
    ResponseResult(tasks, response_proto)


def main():
  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger('worker.main')
  while True:
    try:
      PullTask()
    except Exception as e:
      logger.error(e)
    time.sleep(30)


if __name__ == '__main__':
  main()
