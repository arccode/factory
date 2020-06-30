# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Retrieve parameter files from factory server.

Description
-----------
This pytest retrieves files uploaded to parameter space on factory server.
Pytests with freuquenly modified config files can use this test to download
latest configs before running tests.

To locate config files, assign ``source_namespace`` to directory path of files
relatively to root directory(i.e. ``Current directory`` on factory server) and
assign ``source_file`` to config file name. If targeting all files under given
namespace, no need to assign ``source_file``.

To store config files, assign ``destination_namespace`` to an absolute path on
target machine(e.g. DUT, test station). Default is ``/tmp``.

Test Procedure
--------------
Make sure DUT is connected to factory server, and files are uploaded to server.
Wait for the files to be downloaded.

Dependency
----------
Nothing special.
This test uses only server components in Chrome OS Factory Software.

Examples
--------
Assume updating config file ``testplan.csv`` for ``rf_graphyte`` test, and this
file is uploaded to ``graphyte`` namespace on factory server. Destination path
on test station is ``/usr/local/graphyte/config_files``.

The JSON config with main pytest can be::

  {
    "subtests": [
      {
        "pytest_name": "retrieve_parameter",
        "args": {
          "source_namespace": "/graphyte",
          "source_file": "testplan.csv",
          "destination_namespace": "/usr/local/graphyte/config_files"
        }
      },
      "rf_graphyte"
    ]
  }

Assume updating files ``vswr_config.yaml`` and ``vswr_config_postpress.yaml``
for ``vswr`` test. These files should be uploaded to a directory path on factory
server, and suppose this directory is ``dut1/vswr``. Destination path on DUT for
these files is ``/usr/local/factory/py/test/pytests/vswr``.

The JSON config with main pytest can be::

  {
    "subtests": [
      {
        "pytest_name": "retrieve_parameter",
        "args": {
          "source_namespace": "/dut1/vswr",
          "destination_namespace": "/usr/local/factory/py/test/pytests/vswr"
        }
      },
      "vswr"
    ]
  }
"""

import logging
import tarfile

from cros.factory.test import server_proxy
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


_DISPLAY_MSG_PERIOD = 0.5


class RetrieveParameterError(Exception):
  """Retrieve parameter error."""


class RetrieveParameter(test_case.TestCase):

  ARGS = [
      Arg('source_namespace',
          str,
          'The path to retrieve parameter files.',
          default='/'),
      Arg('source_file',
          str, 'Target parameter file name; '
          '``None`` if targeting all files under given namespace.',
          default=None),
      Arg('destination_namespace',
          str,
          'The path on DUT to save parameter files to.',
          default='/tmp'),
  ]

  def setUp(self):
    self._server = None
    self._frontend_proxy = self.ui.InitJSTestObject('RetrieveParameterTest')
    self.args.source_namespace = self.args.source_namespace.strip('/')
    self.args.source_namespace = self.args.source_namespace or None

  def runTest(self):
    self._frontend_proxy.DisplayStatus('Try connecting to server...')
    try:
      self._server = server_proxy.GetServerProxy(timeout=5)
      self._server.Ping()
    except Exception:
      logging.exception('Retrieve Parameter')
      self._handleError('Failed to connect to server')

    self._frontend_proxy.DisplayStatus('Try downloading files...')
    try:
      content = self._server.GetParameters(self.args.source_namespace,
                                           self.args.source_file).data
    except Exception:
      logging.exception('Retrieve Parameter')
      self._handleError('Namespace or file not found')

    with file_utils.UnopenedTemporaryFile() as tar_path:
      file_utils.WriteFile(tar_path, content)
      tar_file = tarfile.open(tar_path)
      file_utils.TryMakeDirs(self.args.destination_namespace)
      self._frontend_proxy.DisplayStatus('Files downloaded:')
      for member in tar_file:
        tar_file.extract(member, self.args.destination_namespace)
        logging.info('Donwload file: %s', member.name)
        self._frontend_proxy.DisplayAppendFiles(member.name)

    self.Sleep(_DISPLAY_MSG_PERIOD)

  def _handleError(self, message):
    self._frontend_proxy.DisplayError(message)
    self.Sleep(_DISPLAY_MSG_PERIOD)
    raise RetrieveParameterError(message)
