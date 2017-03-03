# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Writes VPD values which are from AB-sub line fixtures.

In AB-sub line, devices may have several calibrated data need to be written
into VPD sections. This test case will be used in FATP test list to read
VPD data from shop floor / Umpire server by using HTTP GET request.
"""

import time
import unittest
import urllib
import urllib2
import urlparse
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import schema

_MSG_VPD_INFO = i18n_test_ui.MakeI18nLabelWithClass(
    'Please scan the panel serial number and press ENTER.', 'vpd-info')

_HTML_VPD = """
<div id="vpd_title"></div>
<br>
<input id="scan-value" type="text" size="20">
<br>
<div id="scan-status"></div>
"""

_CSS_VPD = """
  .vpd-info { font-size: 2em; }
"""

_JS_VPD = """
window.onload = function(event) {
  document.getElementById('scan-value').focus();
}

function setClear() {
  scan_obj = document.getElementById('scan-value');
  scan_obj.disabled = false;
  scan_obj.value = "";
  scan_obj.focus();
}
"""


class GetPanelVPDTest(unittest.TestCase):

  """Gets VPD of the panel from shop floor / Umpire server.

  VPD is obtained by HTTP GET with panel's serial number as key.
  """

  ARGS = [
      Arg('hostname', str, 'Host name or IP address', optional=True),
      Arg('port', int, 'HTTP Request port', default=80),
      Arg('service_path', str, 'HTTP Request service path', default='getvpd'),
  ]
  SCHEMA = schema.Dict('VPD',
                       schema.Scalar('key', str), schema.Scalar('Value', str))

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS_VPD)
    self.template.SetState(_HTML_VPD)
    self.ui.RunJS(_JS_VPD)
    self.ui.BindKeyJS(test_ui.ENTER_KEY,
                      'scan_obj = document.getElementById("scan-value");'
                      'test.sendTestEvent("scan_value", scan_obj.value);'
                      'scan_obj.disabled = true;')
    self.ui.SetHTML(_MSG_VPD_INFO, id='vpd_title')
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)
    self.url = None

    self.GenURL()

  def GenURL(self):
    """Generates correct HTTP URL."""
    if self.args.hostname is None:
      u = urlparse.urlparse(shopfloor.get_server_url())
      self.args.hostname = u.hostname

    self.url = urlparse.urlunparse((
        'http', '%s:%d' % (self.args.hostname, self.args.port),
        self.args.service_path, '', '', ''))

  def SetStatus(self, msg):
    """Sets status on the UI."""
    msg = i18n_test_ui.MakeI18nLabelWithClass(msg, 'vpd-info')
    self.ui.SetHTML(msg, id='scan-status')

  def HandleScanValue(self, event):
    """Handles scaned value."""
    scan_value = str(event.data).strip()
    if not scan_value:
      self.SetStatus(_('The scanned value is empty.'))
      self.ui.CallJSFunction('setClear')
      return

    data = urllib.urlencode({'serial': scan_value, 'action': 'getvpd'})
    try:
      filehandle = urllib2.urlopen(self.url + '?' + data)
    except urllib2.URLError as e:
      self.SetFail('HTTP GET request error: %s' % e.reason)
    else:
      data = filehandle.read()
      self.WriteVPD(data)
      self.ui.Pass()

  def WriteVPD(self, data):
    """Checks data and write into RO VPD.

    Args:
      data: 'None' string or a yaml format dictionary
    """
    if data == 'None':
      self.SetStatus(_('No VPD updated'))
      time.sleep(1)
      return
    vpd_setting = yaml.load(data)
    self.SetStatus(_('Writing to VPD. Please wait...'))
    try:
      self.SCHEMA.Validate(vpd_setting)
    except schema.SchemaException as e:
      self.SetFail('VPD format error: %r' % e)
    else:
      self.vpd.vpd.ro.Update(vpd_setting)

  def SetFail(self, msg):
    self.ui.Fail(msg)

  def runTest(self):
    self.ui.Run()
