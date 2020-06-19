# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os.path
import typing

from google.protobuf import text_format
import yaml

# pylint: disable=no-name-in-module
from cros.factory.probe_info_service.app_engine import client_payload_pb2
from cros.factory.probe_info_service.app_engine import stubby_pb2
# pylint: enable=no-name-in-module
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata')


FAKE_RUNTIME_PROBE_PATH = os.path.join(TESTDATA_DIR, 'fake_runtime_probe')


def _ReadTestdataFile(testdata_filename, encoding='utf-8'):
  return file_utils.ReadFile(os.path.join(TESTDATA_DIR, testdata_filename),
                             encoding=encoding)


def LoadComponentProbeInfo(testdata_name):
  testdata_filename = 'component_probe_info-%s.prototxt' % testdata_name
  instance = stubby_pb2.ComponentProbeInfo()
  text_format.Parse(_ReadTestdataFile(testdata_filename), instance)
  return instance


def LoadProbeInfoParsedResult(testdata_name):
  testdata_filename = 'probe_info_parsed_result-%s.prototxt' % testdata_name
  instance = stubby_pb2.ProbeInfoParsedResult()
  text_format.Parse(_ReadTestdataFile(testdata_filename), instance)
  return instance


def LoadProbeStatementString(testdata_name) -> str:
  testdata_filename = 'probe_statement-%s.json' % testdata_name
  return _ReadTestdataFile(testdata_filename)


def LoadRawProbedOutcome(testdata_name) -> bytes:
  testdata_filename = 'probed_outcome-%s.prototxt' % testdata_name
  return _ReadTestdataFile(testdata_filename, encoding=None)


def LoadProbedOutcome(testdata_name):
  instance = client_payload_pb2.ProbedOutcome()
  text_format.Parse(LoadRawProbedOutcome(testdata_name), instance)
  return instance


class FakeProbedOutcomeInfo:
  def __init__(self, testdata_name):
    testdata_filename = 'fake_probed_outcome_info-%s.yaml' % testdata_name
    raw_data = yaml.load(_ReadTestdataFile(testdata_filename))
    self.component_testdata_names: typing.List[str] = raw_data[
        'component_testdata_names']
    self.envs: typing.Mapping[str, str] = raw_data['envs']
    self.probed_outcome = client_payload_pb2.ProbedOutcome()
    self.probe_config_payload: str = raw_data['probe_config_payload']

    text_format.Parse(raw_data['probed_outcome_prototxt'], self.probed_outcome)
