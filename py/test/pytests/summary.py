#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Displays a status summary for all tests in the current section
(up to, but not including, this test).

For example, if the test tree is

SMT
  ...
Runin
  A
  B
  C
  report (this test)
  shutdown

...then this test will show the status summary for A, B, and C.
'''

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui

CSS = '''
table {
  margin-left: auto;
  margin-right: auto;
  padding-bottom: 1em;
}
th, td {
  padding: 0 1em;
}
'''

class Report(unittest.TestCase):
  def runTest(self):
    test_list = self.test_info.ReadTestList()
    test = test_list.lookup_path(self.test_info.path)
    states = factory.get_state_instance().get_test_states()

    ui = test_ui.UI(css=CSS)
    ui.EnablePassFailKeys()

    statuses = []

    table = []
    for t in test.parent.subtests:
      if t == test:
        break

      state = states.get(t.path)

      table.append('<tr class="test-status-%s"><th>%s</th><td>%s</td></tr>'
                   % (state.status,
                      test_ui.MakeTestLabel(t),
                      test_ui.MakeStatusLabel(state.status)))
      statuses.append(state.status)

    overall_status = factory.overall_status(statuses)

    html = [
        '<div class="test-vcenter-outer"><div class="test-vcenter-inner">',
        test_ui.MakeLabel('Test Status for %s:' % test.parent.path,
                          u'%s 測試結果列表：' % test.parent.path),
        '<div class="test-status-%s" style="font-size: 300%%">%s</div>' % (
            overall_status, test_ui.MakeStatusLabel(overall_status)),
        '<table>',
        ] + table + [
        '</table>',
        '<a onclick="onclick:window.test.pass()" href="#">',
        test_ui.MakeLabel('Click or press SPACE to continue',
                          u'點擊或按空白鍵繼續'),
        '</a>',
        '</div></div>',
        ]

    ui.SetHTML(''.join(html))
    ui.Run()
