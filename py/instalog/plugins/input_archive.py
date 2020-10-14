#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input archive plugin.

Import all events from archives which are made by output_archive.

The archive name:
  'InstalogEvents_' + year + month + day + hour + minute + second

The archive structure:
  InstalogEvents_YYYYmmddHHMMSS.tar.gz
    InstalogEvents_YYYYmmddHHMMSS/
      events.json
      attachments/  # Will not have this dir if no attachment.
        000_${EVENT_0_ATTACHMENT_0_NAME}
        000_${EVENT_0_ATTACHMENT_1_NAME}
        001_${EVENT_1_ATTACHMENT_0_NAME}
        001_${EVENT_1_ATTACHMENT_1_NAME}
        ...
"""

# TODO(kitching): Add a unittest.

import glob
import os
import tarfile

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils


class InputArchive(plugin_base.InputPlugin):

  ARGS = [
      Arg('path', str,
          'Path to the set of archives on disk.  Uses glob syntax.  '
          'e.g. "/path/to/InstalogEvents_*.tar.gz"'),
  ]

  def ExtractArchive(self, archive_path, tmp_path):
    """Extracts archive to tmp_path, and checks that events.json exists.

    Returns:
      json_path: The path of log file in tmp_path.
    """
    with tarfile.open(archive_path, 'r:gz') as tar:
      tar.extractall(tmp_path)
    archive_name = os.path.basename(archive_path)
    # Remove '.tar.gz'
    dir_name = archive_name.split(os.extsep)[0]
    json_path = os.path.join(tmp_path, dir_name, 'events.json')
    if os.path.isfile(json_path):
      return json_path
    self.error('File "%s" does not have event.json', archive_name)
    raise IOError

  def ProcessArchive(self, archive_path):
    """Extracts archive to tmp_path, then parses and emits events within."""
    self.info('Processing archive %s...', archive_path)
    with file_utils.TempDirectory(prefix='input_archive_') as tmp_path:
      try:
        json_path = self.ExtractArchive(archive_path, tmp_path)
        if not self.ParseAndEmit(json_path):
          self.error('Emit failed!')
          raise IOError
      except Exception:
        # We might not have permission to access this file, or there could be
        # some other IO problem, or the tarfile was broken.
        self.exception('Exception while accessing file, check permissions, '
                       'files in archive, and "path" argument.')
        raise

  def Main(self):
    """Main thread of the plugin."""
    archive_paths = sorted(glob.glob(self.args.path))
    self.info('Scanned for archives, %d files detected', len(archive_paths))
    for archive_path in archive_paths:
      self.ProcessArchive(archive_path)
    self.info('Finished importing all archives')

  def ParseAndEmit(self, path):
    """Parses lines in path to events, and emits to Instalog.

    Returns:
      Result from the Emit call (boolean representing its success).
    """
    events = []
    event_dir = os.path.dirname(path)
    with open(path, 'r') as f:
      for line in f:
        event = self.ParseEvent(path, line)
        for att_id, att_path in event.attachments.items():
          event.attachments[att_id] = os.path.join(event_dir, att_path)
        events.append(event)
      self.info('Parsed %d events', len(events))
    return self.Emit(events)

  def ParseEvent(self, path, line):
    """Returns an Instalog Event parsed from line.

    Args:
      path: Path to the log file in question.
      line: The JSON line to be parsed.
            May include trailing \r and \n characters.
    """
    try:
      return datatypes.Event.Deserialize(line)
    except Exception:
      self.error('Encountered invalid line "%s" in %s, aborting import',
                 line.rstrip(), path, exc_info=True)
      raise


if __name__ == '__main__':
  plugin_base.main()
