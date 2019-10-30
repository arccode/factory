# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import logging
import time

from google.cloud import pubsub_v1  # pylint: disable=import-error, no-name-in-module
from googleapiclient import discovery  # pylint: disable=import-error

import factory_common  # pylint: disable=unused-import
from cros.factory.bundle_creator.docker import config  # pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import factorybundle_pb2  # pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import util


RESPONSE_CALLBACK = '/_ah/stubby/FactoryBundleService.ResponseCallback'
ACK_DEADLINE = 600


def ResponseResult(tasks, response_proto):
  tasks.create(parent=config.RESPONSE_QUEUE,
               body={
                   'task': {
                       'app_engine_http_request': {
                           'http_method': 'POST',
                           'relative_uri': RESPONSE_CALLBACK,
                           'body': base64.b64encode(
                               response_proto.SerializeToString())}}}
              ).execute()


def PullTask():
  logger = logging.getLogger('main.pulltask')
  # pylint: disable=unexpected-keyword-arg
  cloudtasks = discovery.build('cloudtasks', 'v2beta3', cache_discovery=False)
  tasks = cloudtasks.projects().locations().queues().tasks()
  subscriber = pubsub_v1.SubscriberClient()
  subscription_path = subscriber.subscription_path(
      config.PROJECT, config.SUBSCRIPTION)
  try:
    response = subscriber.pull(subscription_path, max_messages=1)

    if response:
      received_message = response.received_messages[0]
      subscriber.acknowledge(subscription_path, [received_message.ack_id])
      request_proto = factorybundle_pb2.CreateBundleRpcRequest.FromString(
          received_message.message.data)
      gs_path = util.CreateBundle(request_proto)

      response_proto = factorybundle_pb2.WorkerResult()
      response_proto.status = factorybundle_pb2.WorkerResult.NO_ERROR
      response_proto.original_request.MergeFrom(request_proto)
      response_proto.gs_path = gs_path
      ResponseResult(tasks, response_proto)
  except util.CreateBundleException as e:
    logger.error(e)

    response_proto = factorybundle_pb2.WorkerResult()
    response_proto.status = factorybundle_pb2.WorkerResult.FAILED
    response_proto.original_request.MergeFrom(request_proto)
    response_proto.error_message = str(e)
    ResponseResult(tasks, response_proto)


def main():
  logging.basicConfig()
  logger = logging.getLogger('main')
  logger.setLevel(logging.INFO)
  while True:
    try:
      PullTask()
    except Exception as e:
      logger.error(e)
    time.sleep(30)


if __name__ == '__main__':
  main()
