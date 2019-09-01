#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest
import yaml

import factory_common  # pylint: disable=unused-import

from cros.factory.hwid.v2 import convert_to_v2

HWDB_DIR = os.path.join(os.environ["CROS_WORKON_SRCROOT"], "src", "platform",
                        "factory", "py", "hwid", "v2")
V1_DIR = os.path.join(HWDB_DIR, "convert_to_v2_test_files")
V15_FILE = os.path.join(HWDB_DIR, "convert_to_v2_test_files", "v15_TEST_FILE")
OUTPUT_FILE = os.path.join(HWDB_DIR, "convert_to_v2_test_files", "output_file")


class ConvertToV2Test(unittest.TestCase):

  def testConvertV1Dir(self):
    """Test v1 convert script."""
    convert_to_v2.ConvertV1Dir(V1_DIR, OUTPUT_FILE)
    v2_file = open(OUTPUT_FILE, "r")
    v2_yaml = yaml.load(v2_file)
    v2_file.close()
    os.remove(OUTPUT_FILE)

    boms = ["SAMS_TEST-ALFA", "SAMS_TEST-BETA", "SAMS_TEST-CHARLIE",
            "SAMS_TEST-DELTA"]

    for bom in boms:
      # Test if all of the boms are in the file, and named correctly
      self.assertIn(bom, v2_yaml["boms"])

      # Test if all of the boms have these common component classes
      self.assertIn("audio_codec", v2_yaml["boms"][bom]["primary"]
                    ["components"])
      self.assertIn("cpu", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("dram", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("embedded_controller", v2_yaml["boms"][bom]["primary"]
                    ["components"])
      self.assertIn("flash_chip", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("keyboard", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("touchpad", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("wireless", v2_yaml["boms"][bom]["primary"]["components"])

      # Test if all of the boms have this common component
      self.assertEqual("smsc_fdc37m81x_(id=0x4d,_rev=0x01)", v2_yaml[
          "boms"][bom]["primary"]["components"]["embedded_controller"])
      self.assertEqual("2gb_sku", v2_yaml["boms"][bom]["primary"]["components"]
                       ["dram"])

      # Test if all of the boms have this common variant
      self.assertIn("AA", v2_yaml["boms"][bom]["variants"])

      # Test if all of the boms are listed under the deprecated hwid status
      self.assertIn(bom + " AA-*", v2_yaml["hwid_status"]["deprecated"])

    # Test if missing component classes are listed in classes_missing
    self.assertIn("3g", v2_yaml["boms"]["SAMS_TEST-BETA"]["primary"]
                  ["components"])
    self.assertIn("3g", v2_yaml["boms"]["SAMS_TEST-ALFA"]["primary"]
                  ["classes_missing"])
    self.assertIn("3g", v2_yaml["boms"]["SAMS_TEST-CHARLIE"]["primary"]
                  ["classes_missing"])
    self.assertIn("3g", v2_yaml["boms"]["SAMS_TEST-DELTA"]["primary"]
                  ["classes_missing"])

    # Test if AA is in variants
    self.assertIn("AA", v2_yaml["variants"])

  def testConvertV15(self):
    """Test v1.5 convert script."""
    v15_file = open(V15_FILE, "r")
    v15_yaml = yaml.load(v15_file)
    v15_file.close()
    v2_yaml = convert_to_v2.ConvertV15YamlToV2Yaml(v15_yaml)

    boms = ["BLUE", "GREEN", "RED", "YELLOW"]

    for bom in boms:
      # Test if all of the boms are in the file, and named correctly
      self.assertIn(bom, v2_yaml["boms"])

      # Test if all of the boms have these common component classes
      self.assertIn("audio_codec", v2_yaml["boms"][bom]["primary"]
                    ["components"])
      self.assertIn("cpu", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("dram", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("flash_chip", v2_yaml["boms"][bom]["primary"]["components"])
      self.assertIn("wireless", v2_yaml["boms"][bom]["primary"]["components"])

      # Test if all of the boms have this common component
      self.assertEqual("dram_4gb", v2_yaml["boms"][bom]["primary"]["components"]
                       ["dram"])
      self.assertEqual("winbond_w25q64", v2_yaml["boms"][bom]["primary"]
                       ["components"]["flash_chip"])

      # Test if the same variants in the v1.5 file are in the v2 file
      for var in v15_yaml["hwid_map"][bom]["variant_list"]:
        self.assertIn(var, v2_yaml["boms"][bom]["variants"])

    # Test if the same statuses in the v1.5 file are in the v2 file
    statuses = ["deprecated", "supported"]
    for status in statuses:
      for hwid in v15_yaml["hwid_status_map"][status]:
        hwid_split = hwid.rpartition("-")
        self.assertIn("{0} *-{1}".format(hwid_split[0], hwid_split[2]),
                      v2_yaml["hwid_status"][status])
    # Test for an equal number of initial configs, variants, and volatiles
    self.assertEqual(len(v15_yaml["initial_config_map"]),
                     len(v2_yaml["initial_configs"]))
    self.assertEqual(len(v15_yaml["variant_map"]), len(v2_yaml["variants"]))
    self.assertEqual(len(v15_yaml["volatile_map"]), len(v2_yaml["volatiles"]))

    # Test that volatile values are in the correct format
    for vol, value in v2_yaml["volatile_values"].items():
      if "ro_ec_firmware" in vol:
        self.assertTrue("WQA01" in value.rpartition("#")[2])
      elif "ro_main_firmware" in vol:
        self.assertTrue("Google_Lumpy.2" in value.rpartition("#")[2])

if __name__ == "__main__":
  unittest.main()
