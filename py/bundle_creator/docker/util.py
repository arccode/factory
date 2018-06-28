# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import datetime
import logging
import os
import os.path
import subprocess
import uuid
import yaml

from google.cloud import storage  # pylint: disable=import-error
from google.protobuf import text_format  # pylint: disable=import-error

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
# pylint: disable=no-name-in-module
from cros.factory.bundle_creator.docker import config


class CreateBundleException(Exception):
  pass


def CreateBundle(req):
  logger = logging.getLogger('main.createbundle')
  storage_client = storage.Client.from_service_account_json(
      config.SERVICE_ACCOUNT_JSON, project=config.PROJECT)

  logger.info(text_format.MessageToString(req, as_utf8=True, as_one_line=True))

  with file_utils.TempDirectory() as temp_dir:
    os.chdir(temp_dir)
    bundle_name = '{:%Y%m%d_%H%M}_{}'.format(datetime.datetime.now(), req.phase)

    firmware_source = ('release_image/' + req.firmware_source
                       if req.HasField('firmware_source')
                       else 'release_image')
    manifest = {
        'board': req.board,
        'project': req.project,
        'bundle_name': bundle_name,
        'toolkit': req.toolkit_version,
        'test_image': req.test_image_version,
        'release_image': req.release_image_version,
        'firmware': firmware_source,
    }
    with open(os.path.join(temp_dir, 'MANIFEST.yaml'), 'w') as f:
      yaml.dump(manifest, f)
    process = subprocess.Popen(
        ['/usr/local/factory/factory.par', 'finalize_bundle',
         os.path.join(temp_dir, 'MANIFEST.yaml')],
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    output = ''
    while True:
      line = process.stdout.readline()
      output += line
      if line == '':
        break
      logger.info(line.strip())

    if process.wait() != 0:
      raise CreateBundleException(output)

    random_id = uuid.uuid4()
    bucket = storage_client.get_bucket(config.BUNDLE_BUCKET)
    blob = bucket.blob(
        '{}/factory_bundle_{}_{}.tar.bz2'.format(
            random_id, req.project, bundle_name),
        chunk_size=100 * 1024 * 1024)
    blob.upload_from_filename(
        'factory_bundle_{}_{}.tar.bz2'.format(req.project, bundle_name))
    return u'gs://{}/{}/factory_bundle_{}_{}.tar.bz2'.format(
        config.BUNDLE_BUCKET, random_id, req.project, bundle_name)
