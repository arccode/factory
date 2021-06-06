# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import http.client
import textwrap
import unittest
from unittest import mock

# pylint: disable=wrong-import-order, import-error, no-name-in-module
import urllib3.exceptions
# pylint: enable=wrong-import-order, import-error, no-name-in-module

from cros.factory.probe_info_service.app_engine import gerrit_connector


class GerritConnectorTest(unittest.TestCase):
  _HOST = 'chromium'
  _CHANGE_ID = 'Ix042hu1wnketjv0e1rozt5bior71p8v0mfuxpxio'
  _CL_NUMBER = 1770130
  _CL_MESSAGE = 'This is a message.'

  def setUp(self):
    self._mock_helper_patcher = mock.patch(
        'cros.factory.probe_info_service.app_engine'
        '.gerrit_connector.GerritConnectorHelper')
    self._mock_helper = self._mock_helper_patcher.start().return_value
    self.addCleanup(self._mock_helper_patcher.stop)
    self._connector = gerrit_connector.GerritConnector(self._HOST)

  def testGetCLInfo_BasicInfo_CallsExpectedURL(self):
    self._mock_helper.URLOpen.side_effect = (
        gerrit_connector.GerritConnectorError)

    with self.assertRaises(gerrit_connector.GerritConnectorError):
      self._connector.GetCLInfo(self._CHANGE_ID)

    self._mock_helper.URLOpen.assert_called_once_with(
        'GET', (f'https://{self._HOST}-review.googlesource.com'
                f'/changes/{self._CHANGE_ID}'))

  def testGetCLInfo_BasicInfo_ReturnsExpectedResponse(self):
    self._mock_helper.ConvertDataToJson.return_value = {
        'change_id': self._CHANGE_ID,
        '_number': self._CL_NUMBER,
        'status': 'MERGED',
    }

    cl_info = self._connector.GetCLInfo(self._CHANGE_ID)

    expected_cl_info = gerrit_connector.CLInfo(self._CHANGE_ID, self._CL_NUMBER,
                                               gerrit_connector.CLStatus.MERGED,
                                               None)
    self.assertEqual(cl_info, expected_cl_info)

  def testGetCLInfo_WithMessages_CallsExpectedURL(self):
    self._mock_helper.URLOpen.side_effect = (
        gerrit_connector.GerritConnectorError)

    with self.assertRaises(gerrit_connector.GerritConnectorError):
      self._connector.GetCLInfo(self._CHANGE_ID, include_messages=True)

    self._mock_helper.URLOpen.assert_called_once_with(
        'GET', (f'https://{self._HOST}-review.googlesource.com'
                f'/changes/{self._CHANGE_ID}?o=MESSAGES'))

  def testGetCLInfo_WithMessages_ReturnsExpectedResponse(self):
    self._mock_helper.ConvertDataToJson.return_value = {
        'change_id':
            self._CHANGE_ID,
        '_number':
            self._CL_NUMBER,
        'status':
            'MERGED',
        'messages': [{
            'message': self._CL_MESSAGE,
            'author': {
                '_account_id': 107467
            },
        }, ],
    }

    cl_info = self._connector.GetCLInfo(self._CHANGE_ID, include_messages=True)

    expected_cl_info = gerrit_connector.CLInfo(
        self._CHANGE_ID, self._CL_NUMBER, gerrit_connector.CLStatus.MERGED,
        messages=[gerrit_connector.CLMessage(self._CL_MESSAGE, None)])
    self.assertEqual(cl_info, expected_cl_info)

  def testGetCLInfo_WithCLMessagesAndEmails_CallsExpectedURL(self):
    self._mock_helper.URLOpen.side_effect = (
        gerrit_connector.GerritConnectorError)

    with self.assertRaises(gerrit_connector.GerritConnectorError):
      self._connector.GetCLInfo(self._CHANGE_ID, include_messages=True,
                                include_detailed_accounts=True)

    self._mock_helper.URLOpen.assert_called_once_with(
        'GET', (f'https://{self._HOST}-review.googlesource.com'
                f'/changes/{self._CHANGE_ID}?o=MESSAGES&o=DETAILED_ACCOUNTS'))

  def testGetCLInfo_WithCLMessagesAndEmails_ReturnsExpectedResponse(self):
    email = 'foo@bar'
    self._mock_helper.ConvertDataToJson.return_value = {
        'change_id':
            self._CHANGE_ID,
        '_number':
            self._CL_NUMBER,
        'status':
            'MERGED',
        'messages': [{
            'message': self._CL_MESSAGE,
            'author': {
                'email': email
            },
        }, ],
    }

    cl_info = self._connector.GetCLInfo(self._CHANGE_ID, include_messages=True,
                                        include_detailed_accounts=True)

    expected_cl_info = gerrit_connector.CLInfo(
        self._CHANGE_ID, self._CL_NUMBER, gerrit_connector.CLStatus.MERGED,
        messages=[gerrit_connector.CLMessage(self._CL_MESSAGE, email)])
    self.assertEqual(cl_info, expected_cl_info)

  def testGetCLInfo_ParseResponseFailed_RaisesExpectedException(self):
    self._mock_helper.ConvertDataToJson.return_value = {
        'fake_key': 'fake_value',
    }

    with self.assertRaises(gerrit_connector.GerritConnectorError) as e:
      self._connector.GetCLInfo(self._CHANGE_ID)

    self.assertEqual(
        str(e.exception), 'Failed to parse the Gerrit API response')


class GerritConnectorHelperTest(unittest.TestCase):
  _COOKIE = 'o=git-foo@bar=fake_token'
  _URL = 'https://foo.bar'

  def setUp(self):
    self._helper = gerrit_connector.GerritConnectorHelper()

  @mock.patch('google.auth')
  def testGetGerritAuthCookie_GeneralCase_ReturnsExpectedCookie(
      self, mock_google_auth):
    email = 'foo@bar'
    token = 'ZMhb.D.xWPbbBTkiJsPri-KEYyLlLL99zXrnPqotEf1BKgpqmk'

    def _MockGoogleAuthDefault(scopes):
      if 'https://www.googleapis.com/auth/gerritcodereview' in scopes:
        credentials = mock.Mock(service_account_email=email, token=token)
        return (credentials, None)
      raise ValueError('The scopes don\'t contain `gerritcodereview`.')

    mock_google_auth.default.side_effect = _MockGoogleAuthDefault

    cookie = self._helper.GetGerritAuthCookie()

    self.assertEqual(cookie, f'o=git-{email}={token}')

  def testConvertDataToJson_GeneralCase_ReturnsExpectedJsonData(self):
    change_id = 'fake_change_id'
    number = 1234567
    data = textwrap.dedent(f"""\
        )]}}
        {{
            "change_id": "{change_id}",
            "_number": {number}
        }}
        """).encode('utf-8')

    json_data = self._helper.ConvertDataToJson(data)

    self.assertEqual(json_data, {
        'change_id': change_id,
        '_number': number
    })

  def testConvertDataToJson_FormatError_RaisesExpectedException(self):
    data = 'FORMAT_ERROR_DATA'.encode('utf-8')

    with self.assertRaises(gerrit_connector.GerritConnectorError) as e:
      self._helper.ConvertDataToJson(data)

    self.assertEqual(
        str(e.exception), "Response format error: b'FORMAT_ERROR_DATA'")

  @mock.patch('cros.factory.probe_info_service.app_engine'
              '.gerrit_connector.GerritConnectorHelper.GetGerritAuthCookie')
  @mock.patch('urllib3.PoolManager')
  def testURLOpen_GeneralCase_VerifyCookieIsSetCorrectly(
      self, mock_pool_manager_class, mock_get_gerrit_auth_cookie):
    mock_get_gerrit_auth_cookie.return_value = self._COOKIE
    mock_pool_manager = mock_pool_manager_class.return_value
    mock_pool_manager.urlopen.return_value.status = http.client.OK

    self._helper.URLOpen('GET', self._URL)

    mock_pool_manager.headers.__setitem__.assert_called_with(
        'Cookie', self._COOKIE)

  @mock.patch('cros.factory.probe_info_service.app_engine'
              '.gerrit_connector.GerritConnectorHelper.GetGerritAuthCookie')
  @mock.patch('urllib3.PoolManager')
  def testURLOpen_GeneralCase_ReturnsExpectedData(self, mock_pool_manager_class,
                                                  mock_get_gerrit_auth_cookie):
    data = 'RESPONSE_DATA'.encode('utf-8')
    mock_get_gerrit_auth_cookie.return_value = self._COOKIE
    mock_pool_manager = mock_pool_manager_class.return_value
    mock_pool_manager.urlopen.return_value.status = http.client.OK
    mock_pool_manager.urlopen.return_value.data = data

    returned_data = self._helper.URLOpen('GET', self._URL)

    self.assertEqual(returned_data, data)

  @mock.patch('cros.factory.probe_info_service.app_engine'
              '.gerrit_connector.GerritConnectorHelper.GetGerritAuthCookie')
  @mock.patch('urllib3.PoolManager')
  def testURLOpen_ResponseIsNotFound_RaiseExpectedException(
      self, mock_pool_manager_class, mock_get_gerrit_auth_cookie):
    mock_get_gerrit_auth_cookie.return_value = self._COOKIE
    mock_pool_manager = mock_pool_manager_class.return_value
    mock_pool_manager.urlopen.return_value.status = http.client.NOT_FOUND

    with self.assertRaises(gerrit_connector.GerritConnectorError) as e:
      self._helper.URLOpen('GET', self._URL)

    self.assertEqual(str(e.exception), 'Request unsuccessfully with code 404')

  @mock.patch('cros.factory.probe_info_service.app_engine'
              '.gerrit_connector.GerritConnectorHelper.GetGerritAuthCookie')
  @mock.patch('urllib3.PoolManager')
  def testURLOpen_InvalidUrl_RaiseExpectedException(
      self, mock_pool_manager_class, mock_get_gerrit_auth_cookie):
    mock_get_gerrit_auth_cookie.return_value = self._COOKIE
    mock_pool_manager = mock_pool_manager_class.return_value
    mock_pool_manager.urlopen.side_effect = urllib3.exceptions.HTTPError()

    with self.assertRaises(gerrit_connector.GerritConnectorError) as e:
      self._helper.URLOpen('GET', self._URL)

    self.assertEqual(str(e.exception), f'Invalid URL: {self._URL}')


if __name__ == '__main__':
  unittest.main()
