#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

# pylint: disable=import-error, no-name-in-module
from google.protobuf import json_format
from google.protobuf import text_format

import hardware_verifier_pb2
import runtime_probe_pb2


class HwidConverterTest(unittest.TestCase):

  def testHwVerificationSpec(self):
    """Test HwVerificationSpec integrity."""
    spec = hardware_verifier_pb2.HwVerificationSpec()
    spec.component_infos.add(
        component_category=\
            runtime_probe_pb2.ProbeRequest.SupportCategory.Value(
                "audio_codec"),
        component_uuid="sample_uuid1",
        qualification_status=\
            hardware_verifier_pb2.QualificationStatus.Value("REJECTED"))

    spec.component_infos.add(
        component_category=\
            runtime_probe_pb2.ProbeRequest.SupportCategory.Value(
                "storage"),
        component_uuid="sample_uuid2",
        qualification_status=\
            hardware_verifier_pb2.QualificationStatus.Value("UNQUALIFIED"))

    json_out = json_format.MessageToJson(spec, sort_keys=True)
    text_out = text_format.MessageToString(spec, use_index_order=True)

    spec_from_json = hardware_verifier_pb2.HwVerificationSpec()
    json_format.Parse(json_out, spec_from_json)

    spec_from_text = hardware_verifier_pb2.HwVerificationSpec()
    text_format.Merge(text_out, spec_from_text)

    self.assertEqual(spec_from_text, spec)
    self.assertEqual(spec_from_json, spec)

  def testHwVerificationReport(self):
    """Test HwVerificationReport integrity."""
    report = hardware_verifier_pb2.HwVerificationReport()
    report.is_compliant = True
    report.found_component_infos.add(
        component_category=\
            runtime_probe_pb2.ProbeRequest.SupportCategory.Value("audio_codec"),
        component_uuid="sample_uuid1",
        qualification_status=\
            hardware_verifier_pb2.QualificationStatus.Value("REJECTED"))

    report.found_component_infos.add(
        component_category=\
            runtime_probe_pb2.ProbeRequest.SupportCategory.Value("storage"),
        component_uuid="sample_uuid2",
        qualification_status=\
            hardware_verifier_pb2.QualificationStatus.Value("UNQUALIFIED"))

    json_out = json_format.MessageToJson(report, sort_keys=True)
    text_out = text_format.MessageToString(report, use_index_order=True)

    report_from_json = hardware_verifier_pb2.HwVerificationReport()
    json_format.Parse(json_out, report_from_json)

    report_from_text = hardware_verifier_pb2.HwVerificationReport()
    text_format.Merge(text_out, report_from_text)

    self.assertEqual(report_from_text, report)
    self.assertEqual(report_from_json, report)

  def testProbeRequest(self):
    """Test ProbeRequest integrity."""
    request = runtime_probe_pb2.ProbeRequest()
    request.categories.extend([
        runtime_probe_pb2.ProbeRequest.SupportCategory.Value("audio_codec"),
        runtime_probe_pb2.ProbeRequest.SupportCategory.Value("battery"),
        runtime_probe_pb2.ProbeRequest.SupportCategory.Value("storage")
        ])

    json_out = json_format.MessageToJson(request, sort_keys=True)
    text_out = text_format.MessageToString(request, use_index_order=True)

    request_from_json = runtime_probe_pb2.ProbeRequest()
    json_format.Parse(json_out, request_from_json)

    request_from_text = runtime_probe_pb2.ProbeRequest()
    text_format.Merge(text_out, request_from_text)

    self.assertEqual(request_from_text, request)
    self.assertEqual(request_from_json, request)

  def testProbeResult(self):
    """Test ProbeRequest integrity."""
    result = runtime_probe_pb2.ProbeResult()
    result.error = \
        runtime_probe_pb2.ErrorCode.\
        Value('RUNTIME_PROBE_ERROR_PROBE_CONFIG_SYNTAX_ERROR')

    result.audio_codec.add(
        name="audio_codec1_name",
        values=runtime_probe_pb2.AudioCodec.Fields(
            name="audio1_name.value"
            ))

    result.battery.add(
        name="battery1_name",
        values=runtime_probe_pb2.Battery.Fields(
            index=1,
            manufacturer="manufacturer_test",
            model_name="model_test",
            serial_number="serial_number",
            charge_full_design=5,
            charge_full=6,
            charge_now=7,
            voltage_now=8,
            voltage_min_design=9,
            cycle_count_smart=10,
            status_smart=11,
            temperature_smart=12,
            path="battery_path"
            ))

    result.storage.add(
        name="storage1_name",
        values=runtime_probe_pb2.Storage.Fields(
            path="storage_path",
            sectors=2,
            size=3,
            type="storage_type",
            manfid=5,
            name="storage_name",
            prv=7,
            serial=8,
            oemid=9
            ))

    result.audio_codec.add(
        name="audio_codec2_name",
        values=runtime_probe_pb2.AudioCodec.Fields(
            name="audio2_name.value"
            ))

    json_out = json_format.MessageToJson(result, sort_keys=True)
    text_out = text_format.MessageToString(result, use_index_order=True)

    result_from_json = runtime_probe_pb2.ProbeResult()
    json_format.Parse(json_out, result_from_json)

    result_from_text = runtime_probe_pb2.ProbeResult()
    text_format.Merge(text_out, result_from_text)

    self.assertEqual(result_from_text, result)
    self.assertEqual(result_from_json, result)


if __name__ == '__main__':
  unittest.main()
