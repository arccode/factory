# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This test case is a manual test to do audio functions on DUT
# and let operator or engineer mark pass or fail from their own judgement.

"""Tests to manually test audio playback and record quality."""

import json
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import audio_utils

class AudioDiagnosticTest(unittest.TestCase):
  """A test executing audio diagnostic tools.

  This is a manual test run by operator who judges
  pass/fail result according to the heard audio quality.
  """

  def setUp(self):
    """Initializes the UI.

    Setup the UI for displaying diagnostic controls
    and bind events to corresponding tasks at backend.
    """
    self._ui = test_ui.UI()
    self._ui.AddEventHandler('fail', self.Fail)
    self._ui.AddEventHandler('pass', self.Pass)
    self._ui.AddEventHandler('select_cras_node', self.SelectCrasNode)

    self._cras = audio_utils.CRAS()
    self._cras.UpdateIONodes()

    time.sleep(0.5)
    self.UpdateCrasNodes()

  def SelectCrasNode(self, event):
    node_id = event.data.get('id', '')
    self._cras.SelectNodeById(node_id)
    self.UpdateCrasNodes()

  def UpdateCrasNodes(self):
    factory.console.info('UpdateCrasNodes called! once')
    self._cras.UpdateIONodes()
    plugged_nodes = [n for n in self._cras.output_nodes if n.plugged == 'yes']
    self._ui.CallJSFunction('showCrasNodes', 'output',
                            json.dumps(plugged_nodes,
                                       default=lambda o: o.__dict__))
    plugged_nodes = [n for n in self._cras.input_nodes if n.plugged == 'yes']
    self._ui.CallJSFunction('showCrasNodes', 'input',
                            json.dumps(plugged_nodes,
                                       default=lambda o: o.__dict__))

  def Fail(self, event): # pylint:disable=W0613
    self._ui.Fail('Fail with bad audio quality')

  def Pass(self, event): # pylint:disable=W0613
    self._ui.Pass()

  def runTest(self):
    self._ui.Run()
