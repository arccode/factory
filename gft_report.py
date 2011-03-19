#!/usr/bin/env python
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

""" gft_report.py: Device detail reports for factory process.

The reports for factory is currently a python native dict.

You can use CreateReport() to create a native report,
ValidateReport() to check if a native report is valid,
FormatReport() to print a native report in text form,
EncodeReport() to transform a report to ASCII-safe format,
DecodeReport() to covert from an encoded string.
"""

import base64
import gzip
import pprint
import os
import re
import StringIO
import sys

import gft_common
from gft_common import ErrorMsg, VerboseMsg, DebugMsg, ErrorDie


def ParseKeyValueData(pattern, data):
  """Converts a given key-value style into [(key, value)] format.

  Args:
    pattern: A regex pattern to decode key/value pairs
    data: The data to be parsed.

  Returns:
    A { key: value, ... } dict.

  Raises:
    ValueError: When the input is invalid.
  """
  parsed_list = {}
  for line in data.splitlines():
    matched = re.match(pattern, line.strip())
    if not matched:
      raise ValueError("Invalid data: %s" % line)
    (name, value) = (matched.group(1), matched.group(2))
    if name in parsed_list:
      raise ValueError("Duplicated entry: %s" % name)
    parsed_list[name] = value
  return parsed_list


def ParseVPDOutput(output):
  """ Converts "a"="b"\n list into [(a, b)] """
  return ParseKeyValueData('"(.*)"="(.*)"$', output)


def ParseCrossystemOutput(output):
  """ Converts [a   = b  # comment] into [(a, b)] """
  return ParseKeyValueData("^([^ =]*) *= *(.*[^ ]) *# [^#]*$", output)


def EncodeReport(native_report, text_armed=True):
  """ Encodes a native python-dict report into ASCII friendly form. """
  buf = StringIO.StringIO()
  zbuf = gzip.GzipFile(fileobj=buf, mode='wb')
  zbuf.write(FormatReport(native_report) + "\n")
  zbuf.close()
  buf.seek(0)  # prepare for read
  data = buf.read()
  if text_armed:
    data = base64.encodestring(data)
  return data


def DecodeReport(ascii_form, text_armed=True):
  """ Decodes a report in ASCII form into native python dict. """
  data = ascii_form
  if text_armed:
    data = base64.decodestring(data)
  buf = StringIO.StringIO()
  buf.write(data)
  buf.seek(0)  # prepare for read
  zbuf = gzip.GzipFile(fileobj=buf, mode='rb')
  report_text = zbuf.read()
  zbuf.close()
  return eval(report_text)


def FormatReport(native_report):
  """ Returns a pretty-formatted text presentation of the report. """
  return pprint.pformat(native_report)


def ValidateReport(native_report):
  '''Type check the details data.

  Args:
    native_report: A dict object containing the detail report.

  Returns:
    None if validation passed, otherwise a string of reason for failure.
  '''
  mandatory_string_keys = ['hwid',
                           'create_params',
                           'device_timestamp',
                           ]
  mandatory_dict_keys = ['crossystem',
                         'probed_components',
                         'ro_vpd',
                         'rw_vpd',
                         ]
  mandatory_list_keys = ['wp_status',
                         'verbose_log',
                         ]
  if not isinstance(native_report, dict):
    return 'native_report must be a dict'

  # populate key difference
  mandatory_key_set = (set(mandatory_string_keys) |
                       set(mandatory_dict_keys) |
                       set(mandatory_list_keys))
  detail_key_set = set(native_report.keys())
  key_set_delta = detail_key_set ^ mandatory_key_set
  if key_set_delta:
    err_msg = 'detail key sets differ'
    extra = detail_key_set - mandatory_key_set
    if extra:
      err_msg += ', extra keys [%s]' % ', '.join([repr(x) for x in extra])
    missing = mandatory_key_set - detail_key_set
    if missing:
      err_msg += ', missing keys [%s]' % ', '.join([repr(x) for x in missing])
    return err_msg

  # validate value attributes
  for key in mandatory_string_keys:
    if not isinstance(native_report[key], str):
      return 'property %s in report should be a simple string.' % key

  for key in mandatory_dict_keys:
    value = native_report[key]
    if not isinstance(value, dict):
      return 'property %s in report should be a dict.' % key
    # each elements in value should be simple string
    for subkey in value:
      if not isinstance(value[subkey], str):
        return ('property %s.%s in report should be a simple string.' %
                (key, subkey))

  for key in mandatory_list_keys:
    value = native_report[key]
    if not isinstance(value, list):
      return 'property %s in report should be a list.' % key
    # each elements in value should be simple string
    for subvalue in value:
      if not isinstance(subvalue, str):
        return 'property %s in report should be a list of simple strings.' % key
  return None


def CreateReport(create_params,
                 probed_components,
                 verbose_log_path=gft_common.DEFAULT_CONSOLE_LOG_PATH,
                 vpd_source=None,
                 verbose=False):
  """Creates a detail report for current device.

  Collects hwid, vpd, probed components, and attach a timestamp.

  Args:
    create_params: the original command line that creates the report.
    probed_components: A match result from gft_hwcomp.HardwareComponents
    vpd_source: Optional input image for VPD values (None for system)

  Returns:
    A dict mapping keys to details. Example:
    {'hwid': 'ABC',
     'device_timestamp': 'Thu Mar 17 07:39:04 UTC 2011',
     ...}
  """
  report = {}

  # System Hardware ID
  report['create_params'] = ' '.join(create_params)
  report['hwid'] = gft_common.SystemOutput("crossystem hwid").strip()

  # crossystem reports many system configuration data
  report['crossystem'] = ParseCrossystemOutput(
      gft_common.SystemOutput("crossystem").strip())

  # Vital Product Data
  vpd_cmd = '-f %s' % vpd_source if vpd_source else ''
  report['ro_vpd'] = ParseVPDOutput(
      gft_common.SystemOutput("vpd -i RO_VPD -l %s" % vpd_cmd,
                              progress_messsage="Reading RO VPD",
                              show_progress=verbose).strip())
  report['rw_vpd'] = ParseVPDOutput(
      gft_common.SystemOutput("vpd -i RW_VPD -l %s" % vpd_cmd,
                              progress_messsage="Reading RW VPD",
                              show_progress=verbose).strip())

  # Probed hardware components
  report['probed_components'] = dict(
      [(key, ', '.join(value)) for key, value in probed_components.items()])

  # Firmware write protection status
  wp_status_message = (
      'main: %s\nec: %s' %
      (gft_common.SystemOutput('flashrom -p internal:bus=spi --wp-status'),
       gft_common.SystemOutput('flashrom -p internal:bus=lpc --wp-status')))
  report['wp_status'] = wp_status_message.splitlines()

  # TODO(hungte) we may also add these data in future:
  #   rootfs hash, dump_kernel_config, lsb-release from release image,
  #   gooftool version, result of dev_vboot_debug,
  #   /var/log/factory.log and any other customized data

  # Verbose log. Should be prepared before the last step.
  if verbose_log_path and os.path.exists(verbose_log_path):
    verbose_log = gft_common.ReadFile(verbose_log_path).splitlines()
  else:
    verbose_log = ['(Not available)']
  report['verbose_log'] = verbose_log

  # Finally, attach a timestamp. This must be the last entry.
  report['device_timestamp'] = gft_common.SystemOutput("date --utc").strip()
  return report


#############################################################################
# Console main entry
@gft_common.GFTConsole
def main():
  """ Main entry as a utility. """
  # only load the hardware detection and optparse if we're in console.
  import gft_hwcomp
  import glob
  import optparse

  parser = optparse.OptionParser()
  parser.add_option('--debug', action='store_true',
                    help='provide debug messages.')
  parser.add_option('--decode', action='store_true',
                    help='decode a encoded report to human readable format.')
  parser.add_option('--log_path', metavar='PATH',
                    default=gft_common.DEFAULT_CONSOLE_LOG_PATH,
                    help='use the given path for getting verbose logs.')
  parser.add_option('--report_path', metavar='PATH', default='report.gz',
                    help='use this path to read / write reports.')
  parser.add_option('--report_format', metavar='FORMAT', default='gz',
                    help='format of the generated report; '
                         'currently supported values: gz, base64')
  parser.add_option('--db_path', metavar='DB_PATH',
                    help='path pattern for hardware components databases')
  (options, args) = parser.parse_args()
  if args:
    parser.error('Un-expected parameter(s): %s\n' % ' '.join(args))
  if options.debug:
    gft_common.SetDebugLevel(options.debug)

  # Decode
  if options.decode:
    if not options.report_path:
      parser.error('Need --report_path to assign target for decoding.')
    data = gft_common.ReadFile(options.report_path)
    if options.report_format == 'gz':
      text_armed = False
    elif options.report_format == 'base64':
      text_armed = True
    else:
      ErrorDie('gft_report: invalid report format: %s' % options.report_format)
    print FormatReport(DecodeReport(data, text_armed))
    sys.exit(0)

  # Encode
  if not options.db_path:
    parser.error('Need --db_path.')

  # populate db_path
  db_files = glob.glob(options.db_path)
  if not db_files:
    parser.error('No valid files in --db_path (%s)' % options.db_path)

  hwcomp = gft_hwcomp.HardwareComponents(verbose=True)
  hwcomp.initialize()
  best_match = None
  for db_file in db_files:
    VerboseMsg("gft_report: Matching for %s..." % db_file)
    (probed, failure) = hwcomp.match_current_system(db_file)
    if not failure:
      best_match = probed
      break
  if not best_match:
    best_match = probed
  VerboseMsg('gft_report: Found hardware components: %s' %
             hwcomp.pformat(best_match))

  # create the native report
  native_report = CreateReport(sys.argv,
                               best_match,
                               verbose_log_path=options.log_path,
                               vpd_source=hwcomp.load_main_firmware(),
                               verbose=True)
  invalid_message = ValidateReport(native_report)
  assert not invalid_message, "Invalid report: %s" % invalid_message

  # write the text report into stderr, without being logged.
  sys.stdout.flush()
  sys.stderr.write(FormatReport(native_report) + '\n')

  if options.report_format == 'gz':
    data = EncodeReport(native_report, text_armed=False)
  elif options.report_format == 'base64':
    data = EncodeReport(native_report, text_armed=True)
  else:
    ErrorDie('gft_report: invalid report format: %s' % options.report_format)

  if options.report_path:
    print "Saved report to: %s" % options.report_path
    with open(options.report_path, "wb") as report_handle:
      report_handle.write(data)
  else:
    print data


if __name__ == "__main__":
  main()
