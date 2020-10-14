#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output archive plugin.

An archive plugin to backup all events and their attachments to a tar.gz file.

The archive name:
  'InstalogEvents_' + year + month + day + hour + minute + second

The archive structure:
  InstalogEvents_YYYYmmddHHMMSS.tar.gz
    InstalogEvents_YYYYmmddHHMMSS/
      events.json
      attachments/
        ${ATTACHMENT_0_HASH}
        ${ATTACHMENT_1_HASH}
        ${ATTACHMENT_2_HASH}
        ...
"""

import datetime
import os
import shutil
import tarfile

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_file
from cros.factory.instalog.utils import arg_utils
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils


class OutputArchive(output_file.OutputFile):

  ARGS = arg_utils.MergeArgs(
      output_file.OutputFile.ARGS,
      [
          Arg('enable_disk', bool,
              'Whether or not to save the archive to disk.  True by default.',
              default=True),
          Arg('enable_gcs', bool,
              'Whether or not to upload the archive to Google Cloud Storage.  '
              'False by default.',
              default=False),
          Arg('key_path', str,
              'Path to Cloud Storage service account JSON key file.',
              default=None),
          Arg('gcs_target_dir', str,
              'Path to the target bucket and directory on Google Cloud '
              'Storage.',
              default=None),
      ])

  def __init__(self, *args, **kwargs):
    super(OutputArchive, self).__init__(*args, **kwargs)
    self._gcs = None

  def SetUp(self):
    """Sets up the plugin."""
    super(OutputArchive, self).SetUp()
    if not self.args.enable_disk and not self.args.enable_gcs:
      raise ValueError('Please enable at least one of "enable_disk" or '
                       '"enable_gcs"')

    if not self.args.enable_disk and self.args.target_dir:
      raise ValueError('If specifying a "target_dir", "enable_disk" must '
                       'be set to True')

    if not self.args.enable_gcs:
      if self.args.key_path or self.args.gcs_target_dir:
        raise ValueError('If specifying a "key_path" or "gcs_target_dir", '
                         '"enable_gcs" must be set to True')
    if self.args.enable_gcs:
      if not self.args.key_path or not self.args.gcs_target_dir:
        raise ValueError('If "enable_gcs" is True, "key_path" and '
                         '"gcs_target_dir" must be provided')

      from cros.factory.instalog.utils import gcs_utils
      self._gcs = gcs_utils.CloudStorage(self.args.key_path)

  def ProcessEvents(self, base_dir):
    """Archives events which are saved on base_dir."""
    # Create the archive.
    cur_time = datetime.datetime.now()
    archive_name = cur_time.strftime('InstalogEvents_%Y%m%d%H%M%S')
    archive_filename = '%s.tar.gz' % archive_name
    with file_utils.UnopenedTemporaryFile(
        prefix='instalog_archive_', suffix='.tar.gz') as tmp_archive:
      self.info('Creating temporary archive file: %s', tmp_archive)
      with tarfile.open(tmp_archive, 'w:gz') as tar:
        tar.add(base_dir, arcname=archive_name)

      # What should we do with the archive?
      if self.args.enable_gcs:
        gcs_target_dir = self.args.gcs_target_dir.strip('/')
        gcs_target_path = '/%s/%s' % (gcs_target_dir, archive_filename)
        if not self._gcs.UploadFile(
            tmp_archive, gcs_target_path, overwrite=True):
          self.error('Unable to upload to GCS, aborting')
          return False
      if self.args.enable_disk:
        target_path = os.path.join(self.target_dir, archive_filename)
        self.info('Saving archive to: %s', target_path)
        shutil.move(tmp_archive, target_path)
    return True


if __name__ == '__main__':
  plugin_base.main()
