# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import datetime
import json
import os
import re
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


def whitelist(function):
  def function_wrapper(*args, **kwargs):
    loas_peer_username = os.getenv('LOAS_PEER_USERNAME')
    if loas_peer_username != config.ALLOWED_LOAS_PEER_USERNAME:
      raise Exception(
          'LOAS_PEER_USERNAME {} is not allowed'.format(loas_peer_username))
    return function(*args, **kwargs)
  return function_wrapper


class FactoryBundleService(remote.Service):
  # pylint: disable=no-init
  # pylint warns no-init because it can't found the definition of parent class.

  @remote.method(proto.CreateBundleRpcRequest, proto.CreateBundleRpcResponse)
  @whitelist
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
  def ResponseCallback(self, worker_result):
    mail_list = [worker_result.original_request.email]

    if worker_result.status == proto.WorkerResult.Status.NO_ERROR:
      subject = 'Bundle creation success'
      match = re.match(
          r'^gs://{}/(.*)$'.format(config.BUNDLE_BUCKET), worker_result.gs_path)
      download_link = (
          'https://chromeos.google.com/partner/console/DownloadBundle?path={}'
          .format(urllib.quote_plus(match.group(1))) if match else '-')
      request = worker_result.original_request
      items = ['Board: {}\n'.format(request.board)]
      items.append('Device: {}\n'.format(request.project))
      items.append('Phase: {}\n'.format(request.phase))
      items.append('Toolkit Version: {}\n'.format(request.toolkit_version))
      items.append(
          'Test Image Version: {}\n'.format(request.test_image_version))
      items.append(
          'Release Image Version: {}\n'.format(request.release_image_version))
      if request.firmware_source:
        items.append('Firmware Source: {}\n'.format(request.firmware_source))
      items.append('\nDownload link: {}\n'.format(download_link))
      plain_content = ''.join(items)
      unprocessed_html_content = plain_content.replace(
          download_link,
          '<a href="{}">{}</a>'.format(download_link, download_link))
    else:
      subject = 'Bundle creation failed - {:%Y-%m-%d %H:%M:%S}'.format(
          datetime.datetime.now())
      buganizer_link = 'https://issuetracker.google.com/new?component=596923'
      plain_content = ('If you have issues that need help, please use {}\n\n'
                       '{}').format(buganizer_link, worker_result.error_message)
      unprocessed_html_content = plain_content.replace(
          buganizer_link,
          '<a href="{}">{}</a>'.format(buganizer_link, buganizer_link))
      mail_list.append(config.FAILURE_EMAIL)

    html_content = unprocessed_html_content.replace('\n', '<br>').replace(
        ' ', '&nbsp;')
    mail.send_mail(
        sender=config.NOREPLY_EMAIL,
        to=mail_list,
        subject=subject,
        body=plain_content,
        html=html_content)
    return proto.CreateBundleRpcResponse()

  @remote.method(
      proto.GetBundleHistoryRpcRequest, proto.GetBundleHistoryRpcResponse)
  @whitelist
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
      bundle.test_image_version = blob['metadata'].get(
          'Test-Image-Version', '-')
      bundle.release_image_version = blob['metadata'].get(
          'Release-Image-Version', '-')
      bundle.firmware_source = blob['metadata'].get('Firmware-Source', '-')
      project_set = board_set.setdefault(bundle.board, {})
      project_set.setdefault(bundle.project, []).append(bundle)
    response = proto.GetBundleHistoryRpcResponse()
    for board_projects in request.board_projects:
      for project in board_projects.projects:
        bundle_list = board_set.get(board_projects.board_name,
                                    {}).get(project.name, [])
        for bundle in bundle_list:
          response.bundles.append(bundle)
    response.bundles.sort(key=lambda b: b.uploaded_timestamp_ms, reverse=True)
    return response

  @remote.method(
      proto.DownloadBundleRpcRequest, proto.DownloadBundleRpcResponse)
  @whitelist
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
    response.download_link = 'https://storage.cloud.google.com/{}/{}'.format(
        config.BUNDLE_BUCKET, request.path)
    return response


# Map the RPC service and path
app = service.service_mappings([(_SERVICE_PATH, FactoryBundleService)])
