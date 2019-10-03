# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A pytest to wait operators setup network connection.

Description
-----------
The test set up the network interface as the JSON config specified by
``config_name``.

The interface settings are saved in a JSON config file, the JSON schema for this
config file is `py/test/pytests/network_setup/network_config.schema.json`.

If some interface can not be set up, the test prompts the operator to check
whether the network cable is plugged as expected, and rerun the setup.

Test Procedure
--------------
For each network interface specified in config, the test set up the interface
automatically. If everything goes well, the test pass without user interaction.

If the interface can't be set up correctly, the test show error to operator.
Operator can check if cable is plugged as expected, and press space to retry.
The test would fail if space is not pressed within timeout, or the retry fails.

Dependency
----------
``cros.factory.test.utils.connection_manager``, which depends on ``flimflam``.

Examples
--------
An example of the config file::

    --- py/test/pytests/network_setup/fft_network_config.json ---
    {
      "eth1": {
        "address": "10.0.1.3",
        "prefixlen": 24
      },
      "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1/1-1:1.0/net": {
        "address": "10.0.2.1",
        "prefixlen": 24,
        "gateway": "10.0.2.254"
      }
    }

To set up the network using the config file above, add this in test list::

    {
      "pytest_name": "network_setup",
      "args": {
        "config_name": "fft_network_config"
      }
    }

To set up the network using the same config file, but have a 30 seconds timeout
before retries::

    {
      "pytest_name": "network_setup",
      "args": {
        "config_name": "fft_network_config",
        "timeout_secs": 30
      }
    }
"""

import os

from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import connection_manager
from cros.factory.utils import arg_utils
from cros.factory.utils import sync_utils


_ID_SUBTITLE_DIV = 'subtitle'
_ID_MESSAGE_DIV = 'message'
_ID_INSTRUCTION_DIV = 'instruction'

_STATE_HTML = """
<div id='%s'></div>
<div id='%s'></div>
<div id='%s'></div>
""" % (_ID_SUBTITLE_DIV, _ID_MESSAGE_DIV, _ID_INSTRUCTION_DIV)


ErrorCode = connection_manager.ConnectionManagerException.ErrorCode


def _ErrorCodeToMessage(error_code, interface):
  interface = '<b>%s</b>' % interface
  if error_code == ErrorCode.NO_PHYSICAL_LINK:
    return _('No physical link on {interface}', interface=interface)
  if error_code == ErrorCode.INTERFACE_NOT_FOUND:
    return _('Interface {interface} not found', interface=interface)
  if error_code == ErrorCode.NO_SELECTED_SERVICE:
    return _('Interface {interface} not initialized', interface=interface)
  return _('Unknown Error on {interface}', interface=interface)


class NetworkConnectionSetup(test_case.TestCase):
  ARGS = [
      arg_utils.Arg('config_name', str, 'name of the config file.'),
      arg_utils.Arg('timeout_secs', float,
                    'timeout seconds for each interface, default is no timeout',
                    default=None),
  ]

  def runTest(self):
    self.ui.SetState(_STATE_HTML)

    # make config_name absolute path, however, this might not work in PAR
    config_path = os.path.join(os.path.dirname(__file__),
                               self.args.config_name)
    settings = connection_manager.LoadNetworkConfig(config_path)

    proxy = connection_manager.GetConnectionManagerProxy()

    for interface in settings:
      interface_name = settings[interface].pop('interface_name', interface)
      self.ui.SetHTML(
          _('Setting up interface {interface}',
            interface='<b>%s</b>' % interface),
          id=_ID_SUBTITLE_DIV)

      def _TryOnce(interface=interface, interface_name=interface_name):
        try:
          error_code = proxy.SetStaticIP(interface_or_path=interface,
                                         **settings[interface])
        except connection_manager.ConnectionManagerException as e:
          # if proxy is actually a connection manager instance, error code is
          # raised as an exception, rather than return value.
          error_code = e.error_code

        if error_code is None:
          return True
        # Hint operators what might go wrong.
        self.ui.SetHTML(_ErrorCodeToMessage(error_code, interface_name),
                        id=_ID_MESSAGE_DIV)
        return False

      # Try once first, if we success, we don't need to ask operators to do
      # anything.
      try:
        success = _TryOnce()
      except Exception:
        success = False

      if not success:
        # Failed, wait operators to press space when they think cables are
        # connected correctly.
        self.ui.SetHTML(_('Press space to continue'), id=_ID_INSTRUCTION_DIV)
        self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

        # Polling until success or timeout (operators don't need to press
        # space anymore).
        sync_utils.PollForCondition(_TryOnce,
                                    timeout_secs=self.args.timeout_secs)
