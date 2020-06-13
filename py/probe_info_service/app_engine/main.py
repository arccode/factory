# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

# pylint: disable=import-error,no-name-in-module, wrong-import-order
import flask
from google.cloud import logging as gc_logging
# pylint: enable=import-error,no-name-in-module, wrong-import-order

from cros.factory.probe_info_service.app_engine import config
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.probe_info_service.app_engine import stubby_handler


# Setup logging framework based on the environment as early as possible.
_config = config.Config()
if _config.env_type == config.EnvType.LOCAL:
  logging.basicConfig(level=_config.log_level)
else:
  gc_logging.Client().setup_logging(log_level=_config.log_level)


# Initialize the `app` instance.
app = flask.Flask(__name__)
protorpc_utils.RegisterProtoRPCServiceToFlaskApp(
    app, '/_ah/stubby', stubby_handler.ProbeInfoService())


# Start the server when this module is launched directly.
if __name__ == '__main__':
  app.run(host=os.environ.get('PROBE_INFO_SERVICE_HOST', 'localhost'),
          port=os.environ.get('PROBE_INFO_SERVICE_PORT', 8080),
          debug=True)
