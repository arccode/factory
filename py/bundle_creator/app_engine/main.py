# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import flask

from cros.factory.bundle_creator.app_engine import stubby_handler
from cros.factory.bundle_creator.app_engine import protorpc_utils


app = flask.Flask(__name__)


protorpc_utils.RegisterProtoRPCServiceToFlaskApp(
    app, '/_ah/stubby', stubby_handler.FactoryBundleService())


if __name__ == '__main__':
  app.run(host='127.0.0.1', port=8080, debug=True)
