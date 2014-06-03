#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A long-lived command line interface (CLI) that wraps raw logs."""

# TODO(itspeter):
#   switch to cros.factory.hacked_argparse once migration to Umpire is fully
#   rolled-out.
import argparse
import logging
import os
import signal
import sys
import yaml

import archiver

from archiver_config import GenerateConfig, LockSource, locks
from common import IsValidYAMLFile
from twisted.internet import reactor


def _CleanUp():
  global locks  # pylint: disable=W0603
  # Call reactor.stop() from reactor instance to make sure no spawned
  # process is running in parallel.
  logging.info('Stopping archiver...')
  reactor.callLater(1, reactor.stop)  # pylint: disable=E1101

  for _, lock_file_path in locks:
    logging.info('Trying to delete advisory lock on %r', lock_file_path)
    try:
      os.unlink(lock_file_path)
    except OSError:
      logging.error('Lock file %s is already deleted.', lock_file_path)
  locks = []


def CleanUpDecorator(func):
  """Decorator for deleting the markers and other clean-ups in normal flow."""
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    finally:
      _CleanUp()
  return wrapper


def _SignalHandler(unused_signal, unused_frame):
  _CleanUp()


@CleanUpDecorator
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
      'yaml_config', action='store', type=IsValidYAMLFile,
      help='run archiver with the YAML configuration file')
  parser_dryrun.add_argument(
      'yaml_config', action='store', type=IsValidYAMLFile,
      help='path to YAML configuration file')
  args = top_parser.parse_args(argv)

  # Check fields.
  if args.sub_command in ['run', 'dry-run']:
    with open(args.yaml_config) as f:
      logging.debug('Validating fields in %r', args.yaml_config)
      # TODO(itspeter): Complete the remaining logic for archiver.
      # pylint: disable=W0612
      configs = GenerateConfig(yaml.load(f.read()))

    # Try to acquire locks for each config
    for config in configs:
      LockSource(config)

    if args.sub_command == 'dry-run':
      # TODO(itspeter): Additional action for dry-run checking
      return
    # Start the first cycle for each configs in few secs.
    for config in configs:
      # TODO(itspeter): Special clean-up for first cycle.
      reactor.callLater(5, archiver.Archive, config)  # pylint: disable=E1101

    # Register signal handler
    signal.signal(signal.SIGTERM, _SignalHandler)
    signal.signal(signal.SIGINT, _SignalHandler)
    reactor.run()  # pylint: disable=E1101


if __name__ == '__main__':
  # TODO(itspeter): Consider expose the logging level as an argument.
  logging.basicConfig(
      format=('[%(levelname)s] archiver:%(lineno)d %(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  main(sys.argv[1:])
