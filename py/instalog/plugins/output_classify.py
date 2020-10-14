#!/usr/bin/env python3
#
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output classify plugin.

A plugin to classify events to appropriate sub-directory of target directory.

The default structure:
  ${target_dir}/
    YYYYmmdd/
      ${deviceId}/
        events.json
        attachments/
          ${ATTACHMENT_0_HASH}
          ${ATTACHMENT_1_HASH}
          ${ATTACHMENT_2_HASH}
          ...
      ...
    ...
"""

import datetime
import os
import shutil

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_file
from cros.factory.instalog.utils import arg_utils
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import type_utils


DEFAULT_CLASSIFIERS = ['__DAY__', 'deviceId']


def ClassifierOfDay():
  """Gets relative path of subdirectory."""
  # Use local date as classifier.
  current_date = datetime.date.today()
  subdir_name = current_date.strftime('%Y%m%d')
  return subdir_name


CLASSIFIERS_MAPPING = {'__DAY__': ClassifierOfDay}


class OutputClassify(output_file.OutputFile):

  ARGS = arg_utils.MergeArgs(
      output_file.OutputFile.ARGS,
      [
          Arg('classifiers', list,
              'The list of classifiers. A classifier could be a dictionary '
              'path of a event (e.g. "serialNumbers.serial_number") or '
              'in CLASSIFIERS_MAPPING (e.g. "__DAY__").',
              default=DEFAULT_CLASSIFIERS)
      ])

  def __init__(self, *args, **kwargs):
    super(OutputClassify, self).__init__(*args, **kwargs)
    self.subdir_path = None

  def SetUp(self):
    """Sets up the plugin."""
    super(OutputClassify, self).SetUp()
    if self.args.batch_size != 1:
      self.warning('The batch_size should be 1 in classify plugin')
      self.args.batch_size = 1

    for classifier_name in self.args.classifiers:
      if (classifier_name.startswith('__') and
          classifier_name not in CLASSIFIERS_MAPPING):
        raise ValueError('The classifier "%r" is not found' % classifier_name)

  def ProcessEvents(self, base_dir):
    """Classifies events which are saved on base_dir."""
    file_utils.TryMakeDirs(self.subdir_path)
    output_file.MoveAndMerge(base_dir, self.subdir_path)
    return True

  def PrepareEvent(self, event, base_dir):
    """Copies an event's attachments and returns its serialized form."""
    self.subdir_path = self.target_dir
    for classifier_name in self.args.classifiers:
      if classifier_name in CLASSIFIERS_MAPPING:
        classifier = CLASSIFIERS_MAPPING[classifier_name]
        subdir_name = classifier()
      else:
        subdir_name = str(
            type_utils.GetDict(event, classifier_name, '__UNKNOWN__'))
      self.subdir_path = os.path.join(self.subdir_path, subdir_name)

    for att_id, att_path in event.attachments.items():
      if os.path.isfile(att_path):
        att_hash = file_utils.SHA1InHex(att_path)
        att_newpath = os.path.join(output_file.ATT_DIR_NAME, att_hash)
        shutil.copyfile(att_path, os.path.join(base_dir, att_newpath))
        event.attachments[att_id] = att_newpath
    return event.Serialize()


if __name__ == '__main__':
  plugin_base.main()
