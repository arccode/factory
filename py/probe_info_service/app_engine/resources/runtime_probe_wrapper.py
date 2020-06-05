#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
A standalone script that invokes the runtime probe with correct arguments
and collects back the results.
"""

import argparse
import logging
import os
import subprocess
import sys

from google.protobuf import text_format

# pylint: disable=import-error
import client_payload_pb2
# pylint: enable=import-error


_BUNDLE_ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
_METADATA_RELPATH = 'metadata.prototxt'


def _ReadFile(path):
  with open(path, 'r') as f:
    return f.read()


def _WriteFile(path, data):
  with open(path, 'w') as f:
    f.write(data)


def _ResolveFilePathInBundle(relpath):
  return os.path.join(_BUNDLE_ROOT_DIR, relpath)


def _InvokeRuntimeProbe(probe_config_file_relpath):
  _RUNTIME_PROBE_PATH = 'runtime_probe'
  _RUNTIME_PROBE_TIMEOUT = 30
  _RUNTIME_PROBE_KILL_TIMEOUT = 5

  result = client_payload_pb2.InvocationResult()

  probe_config_real_path = _ResolveFilePathInBundle(probe_config_file_relpath)
  logging.info('Invoke %r for probe config %r testing.',
               _RUNTIME_PROBE_PATH, probe_config_real_path)

  cmd_args = [_RUNTIME_PROBE_PATH,
              '--config_file_path=' + probe_config_real_path, '--to_stdout',
              '--verbosity_level=3']
  logging.debug('Run subcommand: %r.', cmd_args)
  try:
    proc = subprocess.Popen(cmd_args, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  except OSError as e:
    result.result_type = result.INVOCATION_ERROR
    result.error_msg = 'Unable to invoke %r: %r.' % (_RUNTIME_PROBE_PATH, e)
    logging.error(result.error_msg)
    return result

  try:
    result.raw_stdout, result.raw_stderr = proc.communicate(
        timeout=_RUNTIME_PROBE_TIMEOUT)
  except subprocess.TimeoutExpired as e:
    logging.error('Timeout for %r: %r.', _RUNTIME_PROBE_PATH, e)
    result.result_type = result.TIMEOUT
    proc.kill()
    try:
      result.raw_stdout, result.raw_stderr = proc.communicate(
          timeout=_RUNTIME_PROBE_KILL_TIMEOUT)
    except subprocess.TimeoutExpired:
      proc.terminate()
      result.raw_stdout, result.raw_stderr = proc.communicate()
  else:
    result.result_type = result.FINISHED
  result.return_code = proc.returncode

  logging.info('Invocation finished, return code: %r.', proc.returncode)
  return result


def Main():
  ap = argparse.ArgumentParser(
      description=('Test the probe statements in the config file by '
                   'executing runtime_probe against it.'))
  ap.add_argument(
      '--output', metavar='PATH', default='-', dest='output_path',
      help=('Specify the path to dump the output or "-" for outputting to '
            'stdout.'))
  ap.add_argument(
      '--verbose', action='store_true', help='Print debug log messages.')
  args = ap.parse_args()

  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

  metadata = text_format.Parse(
      _ReadFile(_ResolveFilePathInBundle(_METADATA_RELPATH)),
      client_payload_pb2.ProbeBundleMetadata())

  result = client_payload_pb2.ProbedOutcome(
      probe_statement_metadatas=metadata.probe_statement_metadatas,
      rp_invocation_result=_InvokeRuntimeProbe(metadata.probe_config_file_path))
  result_str = text_format.MessageToString(result)

  logging.info('Output the final result to the specific destination.')
  if args.output_path == '-':
    sys.stdout.write(result_str)
  else:
    _WriteFile(args.output_path, result_str)

  logging.info('Done.  Please follow the instruction to upload result data for '
               'justification.')


if __name__ == '__main__':
  Main()
