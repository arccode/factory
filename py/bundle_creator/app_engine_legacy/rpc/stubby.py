# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import re
import urllib

from google.appengine.api import mail  # pylint: disable=import-error,no-name-in-module
from protorpc import remote  # pylint: disable=import-error
from protorpc import definition  # pylint: disable=import-error
from protorpc.wsgi import service  # pylint: disable=import-error

definition.import_file_set('rpc/factorybundle.proto.def')
from cros.factory import proto  # pylint: disable=import-error,wrong-import-position

# The config is imported from factory-private repo.
import config  # pylint: disable=import-error,wrong-import-order,wrong-import-position


_SERVICE_PATH = '/_ah/stubby/FactoryBundleService'


class FactoryBundleService(remote.Service):  # pylint: disable=no-init
  # pylint warns no-init because it can't found the definition of parent class.

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
          '<a href="{0}">{0}</a>'.format(download_link))
    else:
      subject = 'Bundle creation failed - {:%Y-%m-%d %H:%M:%S}'.format(
          datetime.datetime.now())
      buganizer_link = 'https://issuetracker.google.com/new?component=596923'
      plain_content = ('If you have issues that need help, please use {}\n\n'
                       '{}').format(buganizer_link, worker_result.error_message)
      unprocessed_html_content = plain_content.replace(
          buganizer_link,
          '<a href="{0}">{0}</a>'.format(buganizer_link))
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


# Map the RPC service and path
app = service.service_mappings([(_SERVICE_PATH, FactoryBundleService)])
