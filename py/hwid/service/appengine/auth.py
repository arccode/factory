# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import functools
import http
import logging

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.probe_info_service.app_engine import protorpc_utils


def HttpCheck(func):
  """Checks if HTTP requests are from known source.

  For /ingestion/* APIs, hwid service only allows cron job requests via GET.
  This source can be checked by HTTP header.
  """

  @functools.wraps(func)
  def _MethodWrapper(  # pylint: disable=inconsistent-return-statements
      *args, **kwargs):
    if CONFIG.env == 'dev':  # for integration test
      return func(*args, **kwargs)

    from_cron = flask.request.headers.get('X-AppEngine-Cron')
    if from_cron:
      logging.info('Allow cron job requests')
      return func(*args, **kwargs)

    flask.abort(http.HTTPStatus.FORBIDDEN)

  return _MethodWrapper


def RpcCheck(func):
  """Checks if RPC requests are from known source.

  For HwidIngest.* stubby APIs, they only allows cloud tasks requests or
  predefined allowlist which includes the New HWID Service or developers.
  """

  @functools.wraps(func)
  def _MethodWrapper(*args, **kwargs):
    if CONFIG.env == 'dev':  # for integration test
      return func(*args, **kwargs)

    from_cloud_task = flask.request.headers.get('X-AppEngine-QueueName')
    if from_cloud_task:
      logging.info('Allow cloud task requests')
      return func(*args, **kwargs)

    loas_peer_username = flask.request.headers.get(
        'X-Appengine-Loas-Peer-Username')
    if loas_peer_username in CONFIG.client_allowlist:
      return func(*args, **kwargs)

    raise protorpc_utils.ProtoRPCException(
        protorpc_utils.RPCCanonicalErrorCode.PERMISSION_DENIED)

  return _MethodWrapper
