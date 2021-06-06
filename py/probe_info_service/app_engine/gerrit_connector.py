# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import abc
import enum
import http.client
import logging
from typing import List, NamedTuple, Optional
import urllib.parse

# pylint: disable=wrong-import-order, import-error, no-name-in-module
import certifi
import google.auth
import urllib3
# pylint: enable=wrong-import-order, import-error, no-name-in-module

from cros.factory.utils import json_utils


class GerritConnectorError(Exception):
  pass


class CLMessage(NamedTuple):
  message: str
  author_email: Optional[str]


class CLStatus(enum.Enum):
  NEW = enum.auto()
  MERGED = enum.auto()
  ABANDONED = enum.auto()


_GERRIT_CL_STATUS_TO_CL_STATUS = {
    'NEW': CLStatus.NEW,
    'MERGED': CLStatus.MERGED,
    'ABANDONED': CLStatus.ABANDONED,
}


class CLInfo(NamedTuple):
  change_id: str
  cl_number: int
  status: CLStatus
  messages: Optional[List[CLMessage]]


class IGerritConnector(abc.ABC):
  """Interface for the connector of a gerrit connector."""

  @abc.abstractmethod
  def GetCLInfo(self, change_id, include_messages,
                include_detailed_accounts) -> CLInfo:
    """Get the information of the specified CL by querying the Gerrit API.

    Args:
      change_id: Identity of the CL to query.
      include_messages: Whether to pull and return the CL messages.
      include_detailed_accounts: Whether to pull and return the email of users
          in CL messages.

    Returns:
      An instance of `CLInfo`.  Optional fields might be `None`.

    Raises:
      GerritConnectorError if error occurs while querying the Gerrit API.
    """
    raise NotImplementedError


class GerritConnector(IGerritConnector):
  """An implementation for the instance running on AppEngine."""

  def __init__(self, host):
    """Create a gerrit connector with the specific review host.

    Args:
      host: A gerrit host name.
    """
    super().__init__()
    self._helper = GerritConnectorHelper()
    self._origin = f'https://{host}-review.googlesource.com'

  def GetCLInfo(self, change_id, include_messages=False,
                include_detailed_accounts=False) -> CLInfo:
    url = f'{self._origin}/changes/{change_id}'
    params = []
    if include_messages:
      params.append(('o', 'MESSAGES'))
    if include_detailed_accounts:
      params.append(('o', 'DETAILED_ACCOUNTS'))
    if params:
      url = url + '?' + urllib.parse.urlencode(params)

    response_data = self._helper.URLOpen('GET', url)
    json_data = self._helper.ConvertDataToJson(response_data)

    def _ConvertGerritCLMessage(json_data) -> CLMessage:
      return CLMessage(
          json_data['message'],
          json_data['author']['email'] if include_detailed_accounts else None)

    try:
      return CLInfo(json_data['change_id'], json_data['_number'],
                    _GERRIT_CL_STATUS_TO_CL_STATUS[json_data['status']],
                    [_ConvertGerritCLMessage(m) for m in json_data['messages']]
                    if include_messages else None)
    except Exception as e:
      logging.debug('Unexpected Gerrit API response for CL info: %r', json_data)
      raise GerritConnectorError(
          'Failed to parse the Gerrit API response') from e


class GerritConnectorHelper:
  """A helper class for the gerrit connector."""

  def GetGerritAuthCookie(self) -> str:
    """Get the OAuth cookie of gerrit code review.

    Returns:
      An string of the cookie.
    """
    credential, unused_project_id = google.auth.default(
        scopes=['https://www.googleapis.com/auth/gerritcodereview'])
    credential.refresh(google.auth.transport.requests.Request())
    return 'o=git-{service_account_name}={token}'.format(
        service_account_name=credential.service_account_email,
        token=credential.token)

  def ConvertDataToJson(self, data) -> dict:
    """Convert the data responded from the Gerrit Rest API to the json type.

    Args:
      data: The string from the HTTP response.

    Returns:
      A deserialized Python object.

    Raises:
      GerritConnectorError if error occurs while converting data.
    """
    try:
      # The response starts with a magic prefix line for preventing XSSI which
      # should be stripped.
      stripped_json = data.split(b'\n', 1)[1]
      return json_utils.LoadStr(stripped_json)
    except Exception:
      raise GerritConnectorError('Response format error: %r' % (data, ))

  def URLOpen(self, method, url):
    """Convert the data responded from the Gerrit Rest API to the json type.

    Args:
      method: The HTTP request method.
      url: The URL to be called.

    Returns:
      A byte string of the HTTP response data.

    Raises:
      GerritConnectorError if the HTTP response isn't ok.
    """
    pool_manager = urllib3.PoolManager(ca_certs=certifi.where())
    pool_manager.headers['Content-Type'] = 'application/json'
    pool_manager.headers['Connection'] = 'close'
    pool_manager.headers['Cookie'] = self.GetGerritAuthCookie()
    try:
      response = pool_manager.urlopen(method, url)
    except urllib3.exceptions.HTTPError:
      raise GerritConnectorError(f'Invalid URL: {url}')
    if response.status != http.client.OK:
      raise GerritConnectorError(
          f'Request unsuccessfully with code {response.status}')
    return response.data
