# -*- coding: utf-8 -*-
#
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
import yaml
import urllib
import urllib2
import urlparse

import factory_common  # pylint: disable=W0611
from cros.factory.schema import Dict, Scalar, SchemaException
from cros.factory.system import vpd
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection

_MSG_VPD_INFO = test_ui.MakeLabel(
    'Please scan the panel serial number and press ENTER.',
    zh='请扫描面板序号後按下 ENTER',
    css_class='vpd-info')

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

window.onkeydown = function(event) {
  if (event.keyCode == 13) {  // 'enter'
    scan_obj = document.getElementById('scan-value');
    test.sendTestEvent("scan_value", scan_obj.value);
    scan_obj.disabled = true;
  }
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
  SCHEMA = Dict('VPD', Scalar('key', str), Scalar('Value', str))

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_VPD)
    self.template.SetState(_HTML_VPD)
    self.ui.RunJS(_JS_VPD)
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

  def SetStatus(self, eng_msg, zh_msg):
    """Sets status on the UI."""
    msg = test_ui.MakeLabel(eng_msg, zh_msg, css_class='vpd-info')
    self.ui.SetHTML(msg, id='scan-status')

  def HandleScanValue(self, event):
    """Handles scaned value."""
    scan_value = str(event.data).strip()
    if not scan_value:
      self.SetStatus('The scanned value is empty.',
                     '扫描编号是空的。')
      self.ui.CallJSFunction('setClear')
      return

    data = urllib.urlencode({'serial': scan_value})
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
      self.SetStatus('No VPD updated', '没有VPD需要更新')
      time.sleep(1)
      return
    vpd_setting = yaml.load(data)
    self.SetStatus('Writing to VPD. Please wait…',
                   '正在写到 VPD，请稍等…')
    try:
      self.SCHEMA.Validate(vpd_setting)
    except SchemaException as e:
      self.SetFail('VPD format error: %r' % e)
    else:
      vpd.ro.Update(vpd_setting)

  def SetFail(self, msg):
    self.ui.Fail(msg)

  def runTest(self):
    self.ui.Run()
