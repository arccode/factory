# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import json
import re
import time
import urllib

from protorpc import remote  # pylint: disable=import-error
from protorpc import definition  # pylint: disable=import-error
from protorpc import protobuf  # pylint: disable=import-error
from protorpc.wsgi import service  # pylint: disable=import-error
from google.appengine.api import app_identity  # pylint: disable=import-error
from google.appengine.api import mail  # pylint: disable=import-error
from google.appengine.api import urlfetch  # pylint: disable=import-error
from googleapiclient.discovery import build  # pylint: disable=import-error

definition.import_file_set('rpc/factorybundle.proto.def')
from cros.factory import proto  # pylint: disable=import-error

import config  # pylint: disable=import-error


_SERVICE_PATH = '/_ah/stubby/FactoryBundleService'


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
        project_id=config.PROJECT,
        topic=config.PUBSUB_TOPIC)
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
      body = self.GenerateSuccessBody(request)
    else:
      subject = 'Bundle creation failed'
      body = request.error_message
    mail.send_mail(
        sender='factory-bundle-noreply@google.com',
        to=request.original_request.email,
        subject=subject,
        body=body)
    return proto.CreateBundleRpcResponse()

  @remote.method(
      proto.GetBundleHistoryRpcRequest, proto.GetBundleHistoryRpcResponse)
  def GetBundleHistory(self, request):
    scope = 'https://www.googleapis.com/auth/devstorage.read_only'
    token = app_identity.get_access_token(scope)

    api_response = urlfetch.fetch(
        'https://www.googleapis.com/storage/v1/b/{}/o'.format(
            config.BUNDLE_BUCKET),
        method=urlfetch.GET,
        headers={'Authorization': 'OAuth {}'.format(token[0])})
    result = json.loads(api_response.content)
    if api_response.status_code != 200:
      raise Exception(result['error']['message'])
    board_set = {}
    for blob in result['items']:
      bundle = proto.Bundle()
      bundle.path = blob['name']
      bundle.board, bundle.project, bundle.filename = blob['name'].split('/')
      # 'generation' from cloud storage is file created timestamp in
      # milliseconds.
      bundle.uploaded_timestamp_ms = int(blob['generation'])
      bundle.creator = blob['metadata'].get('Bundle-Creator', '-')
      bundle.toolkit_version = blob['metadata'].get('Tookit-Version', '-')
      bundle.test_image_version = \
          blob['metadata'].get('Test-Image-Version', '-')
      bundle.release_image_version = \
          blob['metadata'].get('Release-Image-Version', '-')
      bundle.firmware_source = blob['metadata'].get('Firmware-Source', '-')
      project_set = board_set.setdefault(bundle.board, {})
      project_set.setdefault(bundle.project, []).append(bundle)
    response = proto.GetBundleHistoryRpcResponse()
    for board_projects in request.board_projects:
      for project in board_projects.projects:
        bundle_list = board_set \
            .get(board_projects.board_name, {}) \
            .get(project.name, [])
        for bundle in bundle_list:
          response.bundles.append(bundle)
    response.bundles.sort(key=lambda b: b.uploaded_timestamp_ms, reverse=True)
    return response

  @remote.method(
      proto.DownloadBundleRpcRequest, proto.DownloadBundleRpcResponse)
  def DownloadBundle(self, request):
    scope = 'https://www.googleapis.com/auth/devstorage.full_control'
    token = app_identity.get_access_token(scope)

    entity = 'user-{}'.format(request.email)
    request_body = {'role': 'READER'}
    api_response = urlfetch.fetch(
        'https://www.googleapis.com/storage/v1/b/{}/o/{}/acl/{}'.format(
            config.BUNDLE_BUCKET,
            urllib.quote_plus(request.path),
            urllib.quote_plus(entity)),
        method=urlfetch.PATCH,
        payload=json.dumps(request_body),
        headers={
            'Authorization': 'OAuth {}'.format(token[0]),
            'Content-Type': 'application/json'})
    if api_response.status_code != 200:
      raise Exception(json.loads(api_response.content)['error']['message'])

    response = proto.DownloadBundleRpcResponse()
    response.download_link = \
        'https://storage.cloud.google.com/{}/{}'.format(
            config.BUNDLE_BUCKET, request.path)
    return response

  def GenerateSuccessBody(self, work_result):
    """Generate email body if bundle created successfully.

    Args:
      work_result: proto.WorkerResult defined in
          '../../proto/factorybundle.proto'.

    Returns:
      a string of email body.
    """
    path_match = re.match(
        r'^gs://{}/(.*)$'.format(config.BUNDLE_BUCKET), work_result.gs_path)
    download_link = (
        'https://chromeos.google.com/partner/console/DownloadBundle?path={}' \
            .format(urllib.quote_plus(path_match.group(1)))
        if path_match
        else '-')
    req = work_result.original_request
    body = 'Board: %s\n' % req.board
    body += 'Device: %s\n' % req.project
    body += 'Phase: %s\n' % req.phase
    body += 'Toolkit Version: %s\n' % req.toolkit_version
    body += 'Test Image Version: %s\n' % req.test_image_version
    body += 'Release Image Version: %s\n' % req.release_image_version
    if req.firmware_source:
      body += 'Firmware Source: %s\n' % req.firmware_source
    body += '\nDownload link: %s\n' % download_link
    return body


# Map the RPC service and path
app = service.service_mappings([(_SERVICE_PATH, FactoryBundleService)])
