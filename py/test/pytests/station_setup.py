# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Setup a station for station-based test.

Description
-----------
This factory test checks whether properties for a station (Station name, Line
number, Station number) is set, and ask the operator to set the properties if
it's not.

The test relies on the station_setup Goofy plugin to work. See the docstring of
the station_setup Goofy plugin on the configurable options for the test.

Test Procedure
--------------
If all required properties is already filled, and no duplicate station is found
on Overlord, the test passes without any user interaction.

Otherwise, the operator is prompted with a form to fill in the required
properties. After the input, checks would be performed again, and operator
would be prompted again if check fails.

Dependency
----------
The pytest needs to be run in Goofy, and needs the station_setup Goofy plugin
to be enabled.

See `README for Goofy plugin
<https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/goofy/plugins/README.md#Use-a-Plugin>`_
on how to enable a plugin.

This test depends on the plugin named ``"station_setup.station_setup"``.

Examples
--------
To ask the operator to fill the properties of the station when needed::

  OperatorTest(pytest_name='station_setup')
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates


_HTML = """
<div id='main'>
</div>
"""

_JS = """
const StationSetup = test.invocation.goofy.StationSetup;
function onEnter() {
  if (window.isInEnter) {
    return;
  }
  window.isInEnter = true;
  window.update($('main')).then((ret) => {
    if (ret.success) {
      test.pass();
    } else {
      window.isInEnter = false;
    }
  });
}
(async () => {
  const needUpdate = await StationSetup.needUpdate();
  if (!needUpdate) {
    test.pass();
    return;
  }
  const {html, update} = await StationSetup.run();
  window.update = update;
  goog.dom.safe.setInnerHtml($('main'), html);
})();
"""


class StationSetup(unittest.TestCase):
  """The factory test to setup station."""

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)

  def runTest(self):
    self.assertTrue(
        state.get_instance().IsPluginEnabled('station_setup.station_setup'),
        'This pytest needs the station_setup Goofy plugin to be enabled.')

    self._template.SetState(_HTML)
    self._ui.BindKeyJS(test_ui.ENTER_KEY, 'onEnter();')
    self._ui.RunJS(_JS)
    self._ui.Run()
