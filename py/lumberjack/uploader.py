#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A reference demos uploading archives to Google."""

import argparse
import logging
import sys

from common import IsValidYAMLFile

def main(argv):
  top_parser = argparse.ArgumentParser(description='Uploader')
  sub_parsers = top_parser.add_subparsers(
      dest='sub_command', help='available sub-actions')

  parser_start = sub_parsers.add_parser('start', help='start the uploader')
  parser_status = sub_parsers.add_parser(   # pylint: disable=W0612
      'status', help='Show all the activities')
  parser_clean = sub_parsers.add_parser(  # pylint: disable=W0612
      'clean', help='Clear completed history')
  # TODO(itspeter):
  #  Add arguments for status and clean which are running without
  #  an YAML configuration file.

  parser_start.add_argument(
      'yaml_config', action='store', type=IsValidYAMLFile,
      help='start uploader with the YAML configuration file')
  args = top_parser.parse_args(argv)

  # Check fields.
  if args.sub_command == 'start':
    # TODO(itspeter): Implement the logic as design in docs.
    pass
  elif args.sub_command == 'status':
    # TODO(itspeter): Implement the logic as design in docs.
    pass
  elif args.sub_command == 'clean':
    # TODO(itspeter): Implement the logic as design in docs.
    pass

if __name__ == '__main__':
  # TODO(itspeter): Consider expose the logging level as an argument.
  logging.basicConfig(
      format=('[%(levelname)s] archiver:%(lineno)d %(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  main(sys.argv[1:])
