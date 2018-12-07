# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import os
import time

from protorpc import remote  # pylint: disable=import-error
from protorpc import definition  # pylint: disable=import-error
from protorpc import protobuf  # pylint: disable=import-error
from protorpc.wsgi import service  # pylint: disable=import-error
from google.appengine.api import mail  # pylint: disable=import-error
from googleapiclient.discovery import build  # pylint: disable=import-error

definition.import_file_set('rpc/factorybundle.proto.def')
from cros.factory import proto  # pylint: disable=import-error


_SERVICE_PATH = '/_ah/stubby/FactoryBundleService'
_PROJECT_ID = os.environ['APPLICATION_ID'][2:]  # format should be google.com:x
_PUBSUB_TOPIC = os.environ['PUBSUB_TOPIC']


class TimeoutError(Exception):
  pass


def WaitFor(predicate, timeout, interval):
  start_time = time.time()
  while time.time() - start_time < timeout:
    result = predicate()
    if result:
      return result
    time.sleep(interval)
  raise TimeoutError


class FactoryBundleService(remote.Service):
  # pylint: disable=no-init
  # pylint warns no-init because it can't found the definition of parent class.

  @remote.method(proto.CreateBundleRpcRequest, proto.CreateBundleRpcResponse)
  def CreateBundleAsync(self, request):
    pubsub_service = build('pubsub', 'v1')
    topic_path = 'projects/{project_id}/topics/{topic}'.format(
        project_id=_PROJECT_ID,
        topic=_PUBSUB_TOPIC)
    pubsub_service.projects().topics().publish(
        topic=topic_path,
        body={
            'messages': [{
                'data': base64.b64encode(protobuf.encode_message(request)),
            }]
        }
    ).execute()
    return proto.CreateBundleRpcResponse()

  @remote.method(proto.WorkerResult, proto.CreateBundleRpcResponse)
  def ResponseCallback(self, request):
    if request.status == proto.WorkerResult.Status.NO_ERROR:
      subject = 'Bundle creation success'
      body = request.gs_path
    else:
      subject = 'Bundle creation failed'
      body = request.error_message
    mail.send_mail(
        sender='noreply@google.com',
        to=request.original_request.email,
        subject=subject,
        body=body)
    return proto.CreateBundleRpcResponse()

# Map the RPC service and path
app = service.service_mappings([(_SERVICE_PATH, FactoryBundleService)])
