#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input event_log file plugin.

Subclasses InputLogFile to correctly parse an event_log file.
"""

import logging

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import input_log_file

from cros.factory.instalog.external import yaml


_EVENT_HEAD = 'EVENT: '
_EVENT_SEPARATOR = '---\n'


class InputEventlogFile(input_log_file.InputLogFile):

  def GetEventlogStrings(self, lines):
    """Returns a generator that retrieves event_log strings.

    Divides event_log events based on _EVENT_SEPARATOR.

    Args:
      lines: A generator which sequentially yields lines from the log file,
             where each line includes trailing \r and \n characters.
    """
    current_event = ''
    for line in lines:
      current_event += line
      if line == _EVENT_SEPARATOR:
        yield current_event
        current_event = ''
    if current_event != '':
      yield current_event

  def ParseEventlogEvent(self, event_str, source_name=None, source_line_num=1):
    """Converts an event log event string to a nested Python dict.

    A robust event log event parser that takes into account possible corruptions
    that may have occurred during disk writes.

    Example corrupted event:
      EVENT:
      L~~corruption1~~EVENT:
      LOG_ID:
      PRE~~corruption2~~EVENT:  # recover from the last event
      LOG_ID:
      PREFIX:
      SEQ:
      TIME:
      test_property:
      #s
      ---

    In the event that a corrupted (a.k.a. non-parseable event) is found,
    recovery is attempted by finding the last occurrence of 'EVENT:' in
    event_str, and re-parsing from that point onward.  If parsing is successful,
    the corrupted event(s) prior to that point in the string are silently
    ignored.  If parsing is still unsuccessful, None is returned, and event_str
    is completely ignored.  Errors will still be logged using Python's logging
    system.

    source_name and source_line_num are optional, and used for logging purposes
    only.  This could be useful if the caller would like to investigate the
    source of a parsing error.

    Args:
      event_str: String representation of a single event from an event log file.
      source_name: Name or location of the event's event log file.
      source_line_num: The line number in the event log file where this event
                       begins.

    Returns:
      On successful parsing, returns a nested Python dict representing this
      event.  On unrecoverable parsing failure, returns None.

    Raises:
      Exception if any exception other than yaml.parser.ParserError or
      yaml.reader.ReaderError occurs.
    """
    def LogError(logger_name, error_str, relative_end_line_num):
      logger = logging.getLogger(logger_name)
      if source_name:
        error_str += ' from %s' % source_name
      source_end_line_num = source_line_num + relative_end_line_num
      error_str += ' on lines %d to %d' % (source_line_num, source_end_line_num)
      logger.warning(error_str)

    # Remove trailing '---\n'.
    event_str = event_str.rstrip()
    if event_str.endswith(_EVENT_SEPARATOR.rstrip()):
      event_str = event_str[:-len(_EVENT_SEPARATOR.rstrip())]

    output = None
    try:
      output = yaml.load(event_str)
    except yaml.error.YAMLError:
      # Try recovering.  Was the event cut off in the middle?  Attempt to parse
      # from the last occurence of 'EVENT:' until the end of the string.
      recover_event_index = event_str.rfind(_EVENT_HEAD)
      if recover_event_index > 0:
        try:
          # Dropping event(s) that were cut off mid-stream.
          output = yaml.load(event_str[recover_event_index:])

          # Log this error.
          recover_event_line_num = event_str.count(
              '\n', 0, recover_event_index - 1)
          LogError(self.logger.name, 'Dropping corrupted event(s)',
                   recover_event_line_num)
        except yaml.error.YAMLError:
          # `output` will still be None.  Log error below.
          pass

    if output is None:
      # Unrecoverable error.  Completely drop this event, and log this error.
      end_line = event_str.count('\n')
      LogError(self.logger.name, 'Unrecoverable event(s)', end_line)
      return None

    # Verify that our output has the required keys.
    if 'EVENT' not in output or 'TIME' not in output:
      end_line = event_str.count('\n')
      LogError(self.logger.name, 'Dropped event due to missing required KEY',
               end_line)
      return None
    return output

  def ParseEvents(self, path, lines):
    """Returns a generator that creates Instalog Event objects.

    Generator should generate None if any erroneous data was skipped.  This is
    to give ParseAndEmit a chance to check how many bytes have been processed in
    the current batch, and whether it exceeds self.args.batch_max_bytes.

    Args:
      path: Path to the log file in question.
      lines: A generator which sequentially yields lines from the log file,
             where each line includes trailing \r and \n characters.
    """
    event_log_str_gen = self.GetEventlogStrings(lines)
    for event_log_str in event_log_str_gen:
      event_log_dict = self.ParseEventlogEvent(event_log_str, source_name=path)
      if not event_log_dict:
        yield None
      else:
        event_log_dict['__eventlog__'] = True
        yield datatypes.Event(
            self.ParseEventlogEvent(event_log_str, source_name=path))


if __name__ == '__main__':
  plugin_base.main()
