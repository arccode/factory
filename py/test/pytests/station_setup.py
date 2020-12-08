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
<https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/goofy/plugins/README.md#Use-a-Plugin>`_
on how to enable a plugin.

This test depends on the plugin named ``"station_setup.station_setup"``.

Examples
--------
To ask the operator to fill the properties of the station when needed, add this
in test list::

  {
    "pytest_name": "station_setup"
  }
"""

from cros.factory.test import state
from cros.factory.test import test_case


class StationSetup(test_case.TestCase):
  """The factory test to setup station."""

  def runTest(self):
    self.assertTrue(
        state.GetInstance().IsPluginEnabled('station_setup.station_setup'),
        'This pytest needs the station_setup Goofy plugin to be enabled.')

    # All works are done in station_setup_static/station_setup.js, so we just
    # wait the frontend JavaScript ends here.
    self.WaitTaskEnd()
