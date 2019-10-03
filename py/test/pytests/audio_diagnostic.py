# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This test case is a manual test to do audio functions on DUT
# and let operator or engineer mark pass or fail from their own judgement.

"""Tests to manually test audio playback and record quality."""

from cros.factory.test import test_case
from cros.factory.test.utils import audio_utils


class AudioDiagnosticTest(test_case.TestCase):
  """A test executing audio diagnostic tools.

  This is a manual test run by operator who judges
  pass/fail result according to the heard audio quality.
  """

  def setUp(self):
    """Setup CRAS and bind events to corresponding tasks at backend."""
    self.event_loop.AddEventHandler('select_cras_node', self.SelectCrasNode)

    self._cras = audio_utils.CRAS()
    self._cras.UpdateIONodes()

    self.Sleep(0.5)
    self.UpdateCrasNodes()

  def SelectCrasNode(self, event):
    node_id = event.data.get('id', '')
    self._cras.SelectNodeById(node_id)
    self.UpdateCrasNodes()

  def UpdateCrasNodes(self):
    self._cras.UpdateIONodes()
    self.ui.CallJSFunction('showCrasNodes', 'output',
                           [node.__dict__ for node in self._cras.output_nodes])
    self.ui.CallJSFunction('showCrasNodes', 'input',
                           [node.__dict__ for node in self._cras.input_nodes])

  def runTest(self):
    self.ui.CallJSFunction('init')
    self.WaitTaskEnd()
