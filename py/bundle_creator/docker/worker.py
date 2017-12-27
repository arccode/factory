# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import logging
import time

from googleapiclient import discovery  # pylint: disable=import-error

import factory_common  # pylint: disable=unused-import
# pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import config
# pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import factorybundle_pb2
from cros.factory.bundle_creator.docker import util


RESPONSE_CALLBACK = '/_ah/stubby/FactoryBundleService.ResponseCallback'


def PullTask():
  logger = logging.getLogger('main.pulltask')
  # pylint: disable=unexpected-keyword-arg
  cloudtasks = discovery.build('cloudtasks', 'v2beta2', cache_discovery=False)
  tasks = cloudtasks.projects().locations().queues().tasks()
  try:
    response = tasks.lease(parent=config.REQUEST_QUEUE,
                           body={'maxTasks': 1,
                                 'responseView': 'FULL',
                                 'leaseDuration': '3600s'}).execute()

    if response:
      task = response['tasks'][0]
      payload = task['pullMessage']['payload']
      request_proto = factorybundle_pb2.CreateBundleRpcRequest.FromString(
          base64.b64decode(payload))
      gs_path = util.CreateBundle(request_proto)
      tasks.acknowledge(name=task['name'],
                        body={'scheduleTime': task['scheduleTime']}).execute()

      response_proto = factorybundle_pb2.WorkerResult()
      response_proto.status = factorybundle_pb2.WorkerResult.NO_ERROR
      response_proto.original_request.MergeFrom(request_proto)
      response_proto.gs_path = gs_path
      tasks.create(parent=config.RESPONSE_QUEUE,
                   body={
                       'task': {
                           'appEngineHttpRequest': {
                               'httpMethod': 'POST',
                               'relativeUrl': RESPONSE_CALLBACK,
                               'payload': base64.b64encode(
                                   response_proto.SerializeToString())}}}
                  ).execute()
  except util.CreateBundleException as e:
    logger.error(e)
    tasks.acknowledge(name=task['name'],
                      body={'scheduleTime': task['scheduleTime']}
                     ).execute()

    response_proto = factorybundle_pb2.WorkerResult()
    response_proto.status = factorybundle_pb2.WorkerResult.FAILED
    response_proto.original_request.MergeFrom(request_proto)
    response_proto.error_message = e.message
    tasks.create(parent=config.RESPONSE_QUEUE,
                 body={
                     'task': {
                         'appEngineHttpRequest': {
                             'httpMethod': 'POST',
                             'relativeUrl': RESPONSE_CALLBACK,
                             'payload': base64.b64encode(
                                 response_proto.SerializeToString())}}}
                ).execute()


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
