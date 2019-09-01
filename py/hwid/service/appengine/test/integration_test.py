#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for AppEngine Integration."""

import argparse
import logging
import os
import re
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


HOST_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
HOST_APPENGINE_DIR = os.path.dirname(HOST_TEST_DIR)
HOST_FACTORY_DIR = os.path.abspath(
    os.path.join(HOST_APPENGINE_DIR, '../../../..'))
HOST_DEPLOY_DIR = os.path.join(HOST_FACTORY_DIR, 'deploy')
GUEST_FACTORY_DIR = '/usr/src/cros/factory'
DEPLOY_SCRIPT = os.path.join(HOST_DEPLOY_DIR, 'cros_hwid_service.sh')
DEFAULT_DOCKER_IMAGE_NAME = 'appengine_integration:latest'


def _PrepareTests(test_names):
  """Lists test paths.

  Args:
    test_names: A list of test names to run. None for returning all tests.
  Returns:
    A list a test path in docker image.
  """
  def _CanonicalizeTestName(test_name):
    test_name = test_name if test_name.endswith('.py') else test_name + '.py'
    test_path = os.path.join(HOST_APPENGINE_DIR, test_name)
    if not os.path.isfile(test_path):
      raise ValueError('Test %s not exists')
    return test_path

  def _HostToGuest(test_paths):
    """Transform test paths from host to guest."""
    return [
        path.replace(HOST_FACTORY_DIR, GUEST_FACTORY_DIR) for path in test_paths
    ]

  def _ListAllTests():
    return [
        _CanonicalizeTestName(tn)
        for tn in os.listdir(HOST_APPENGINE_DIR)
        if os.path.isfile(os.path.join(HOST_APPENGINE_DIR, tn)) and
        tn.endswith('_test.py')
    ]

  if test_names:
    return _HostToGuest([_CanonicalizeTestName(tn) for tn in test_names])
  else:
    return _HostToGuest(_ListAllTests())


def _BuildDockerImage():
  """Builds docker image and returns the image tag."""
  out = process_utils.CheckOutput([DEPLOY_SCRIPT, 'build'], log=True)
  return re.search(r'^Successfully tagged (\w+:\w+)', out,
                   re.MULTILINE).group(1)


def RunTest(image, test_names):
  """Runs the given tests.

  Args:
    image: A string for docker image name.
    test_names: A list of test names to run.
  Returns:
    True if all tests pass.
  """
  container_id = process_utils.CheckOutput(
      ['docker', 'run', '-d', '-it', image], log=True).strip()

  failed_tests = []
  for tn in test_names:
    p = process_utils.Spawn(
        ['docker', 'exec', container_id, tn],
        read_stdout=True,
        read_stderr=True,
        log=True)
    if p.returncode != 0:
      with open(file_utils.CreateTemporaryFile(), 'w') as f:
        f.write('stdout:\n' + p.stdout_data)
        f.write('\nstderr:\n' + p.stderr_data)
        failed_tests.append((tn, f.name))

  logging.info('[%s/%s] Passed',
               len(test_names) - len(failed_tests), len(test_names))

  for t in failed_tests:
    logging.error('FAILED: %s', t)

  process_utils.LogAndCheckCall(['docker', 'stop', container_id])

  return not failed_tests


def main():
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  parser = argparse.ArgumentParser(description='AppEngine Interation Test')
  parser.add_argument(
      '--no-build',
      action='store_true',
      help='Not building latest docker image, use default image.')
  parser.add_argument('test_names', nargs='*', default=[])
  args = parser.parse_args()

  image = DEFAULT_DOCKER_IMAGE_NAME if args.no_build else _BuildDockerImage()
  tests_to_run = _PrepareTests(args.test_names)
  if not RunTest(image, tests_to_run):
    sys.exit(1)


if __name__ == '__main__':
  main()
