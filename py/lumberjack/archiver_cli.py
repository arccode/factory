#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A long-lived command line interface (CLI) that wraps raw logs."""

# TODO(itspeter): switch to cros.factory.hacked_argparse once migration to
#                 Umpire is fully rolled-out.
import argparse
import logging
import signal
import sys

import twisted
import twisted.internet
import twisted.internet.reactor
import yaml

import archiver
import archiver_config
import common


def _CleanUp():
  """Call archiver_config.CleanUp() and end the reactor."""
  # Call reactor.stop() from reactor instance to make sure no spawned
  # process is running in parallel.
  logging.info('Stopping archiver...')
  # pylint: disable=E1101
  twisted.internet.reactor.callLater(1, twisted.internet.reactor.stop)
  archiver_config.CleanUp()


def _SignalHandler(unused_signal, unused_frame):
  _CleanUp()


def main(argv):
  top_parser = argparse.ArgumentParser(description='Log Archiver')
  sub_parsers = top_parser.add_subparsers(
      dest='sub_command', help='available sub-actions')

  parser_run = sub_parsers.add_parser('run', help='start the archiver')
  parser_dryrun = sub_parsers.add_parser(
      'dry-run', help='verify configuration without actually start archiver')
  # TODO(itspeter):
  #  Add arguments for run-once. run-once can run without a YAML configuration
  #  (i.e. directly from command line.)
  parser_runonce = sub_parsers.add_parser(  # pylint: disable=W0612
      'run-once', help='manually archive specific files')

  parser_run.add_argument(
      'yaml_config', action='store', type=common.IsValidYAMLFile,
      help='run archiver with the YAML configuration file')
  parser_dryrun.add_argument(
      'yaml_config', action='store', type=common.IsValidYAMLFile,
      help='path to YAML configuration file')
  args = top_parser.parse_args(argv)

  # Check fields.
  if args.sub_command in ['run', 'dry-run']:
    with open(args.yaml_config) as f:
      logging.debug('Validating fields in %r', args.yaml_config)
      # TODO(itspeter): Complete the remaining logic for archiver.
      # pylint: disable=W0612
      configs = archiver_config.GenerateConfig(yaml.load(f.read()))

    # Try to acquire locks for each config
    for config in configs:
      archiver_config.LockSource(config)

    if args.sub_command == 'dry-run':
      # TODO(itspeter): Additional action for dry-run checking
      return
    # Start the first cycle for each configs in few secs.
    for config in configs:
      # TODO(itspeter): Special clean-up for first cycle.
      # pylint: disable=E1101
      twisted.internet.reactor.callLater(5, archiver.Archive, config)

    # Register signal handler
    signal.signal(signal.SIGTERM, _SignalHandler)
    signal.signal(signal.SIGINT, _SignalHandler)
    twisted.internet.reactor.run()  # pylint: disable=E1101


if __name__ == '__main__':
  # TODO(itspeter): Consider expose the logging level as an argument.
  logging.basicConfig(
      format=('[%(levelname)5s] %(filename)15s:%(lineno)d '
              '%(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  try:
    main(sys.argv[1:])
  finally:
    _CleanUp()
