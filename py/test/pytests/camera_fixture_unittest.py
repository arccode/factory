#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Please run in chroot:
$ sudo USE='jpeg png' emerge opencv
$ sudo USE='jpeg python' emerge zbar
Otherwise the unittest will be skipped automatically.
"""

import unittest

import factory_common # pylint: disable=W0611

from cros.factory.test.fixture.camera.light_chamber import LightChamber
import cros.factory.test.fixture.camera.perf_tester as camperf


class CameraFixtureTest(unittest.TestCase):
  """Unit test for CameraFixture class."""
  def TestIQ(self):
    """Test Image Quality."""
    #######################
    # Test chart version A
    #######################
    chamber = LightChamber(test_chart_version='A', mock_mode=True,
                           device_index=-1, image_resolution=(1280, 720))
    ref_data = camperf.PrepareTest(chamber.GetTestChartFile())

    self.assertEqual(ref_data.corners.shape[0], 308)
    self.assertEqual(ref_data.edges.shape[0], 308)

    _, gray_img = chamber.ReadSingleFrame()
    success, tar_data = camperf.CheckVisualCorrectness(
        sample=gray_img, ref_data=ref_data, max_image_shift=0.10,
        max_image_tilt=1.0)

    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_data.shift, 0.0103406598935, delta=0.00001)
    self.assertAlmostEqual(tar_data.tilt, 0.361484238478, delta=0.00001)
    self.assertAlmostEqual(tar_data.v_shift[0], -12.75, delta=0.01)
    self.assertAlmostEqual(tar_data.v_shift[1], 8.25, delta=0.01)
    self.assertEqual(tar_data.sample_corners.shape[0], 308)
    self.assertEqual(tar_data.edges.shape[0], 308)

    # TODO(jchuang): test low freq response
    success, tar_ls = camperf.CheckLensShading(
        sample=gray_img, max_shading_ratio=0.40, check_low_freq=False)
    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_ls.lowest_ratio, 0.68819620138, delta=0.00001)

    # TODO(jchuang): test MTF50P
    success, tar_mtf = camperf.CheckSharpness(
        sample=gray_img, edges=tar_data.edges,
        min_pass_mtf=0.3, min_pass_lowest_mtf=0.2,
        use_50p=False, mtf_sample_count=308,
        mtf_patch_width=20) # patch width 20 for 720p
    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_mtf.mtf, 0.53719148, delta=0.00001)
    self.assertAlmostEqual(tar_mtf.min_mtf, 0.3479868, delta=0.00001)

    #######################
    # Test chart version B
    #######################
    chamber = LightChamber(test_chart_version='B', mock_mode=True,
                           device_index=-1, image_resolution=(640, 480))
    ref_data = camperf.PrepareTest(chamber.GetTestChartFile())

    self.assertEqual(ref_data.corners.shape[0], 252)
    self.assertEqual(ref_data.edges.shape[0], 252)

    _, gray_img = chamber.ReadSingleFrame()
    success, tar_data = camperf.CheckVisualCorrectness(
        sample=gray_img, ref_data=ref_data, max_image_shift=0.10,
        max_image_tilt=1.0)

    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_data.shift, 0.03867558, delta=0.00001)
    self.assertAlmostEqual(tar_data.tilt, 0.19532118, delta=0.00001)
    self.assertAlmostEqual(tar_data.v_shift[0], -6.5, delta=0.01)
    self.assertAlmostEqual(tar_data.v_shift[1], -30.25, delta=0.01)
    self.assertEqual(tar_data.sample_corners.shape[0], 252)
    self.assertEqual(tar_data.edges.shape[0], 252)

    success, tar_ls = camperf.CheckLensShading(
        sample=gray_img, max_shading_ratio=0.40, check_low_freq=False)
    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_ls.lowest_ratio, 0.7612925, delta=0.00001)

    success, tar_mtf = camperf.CheckSharpness(
        sample=gray_img, edges=tar_data.edges,
        min_pass_mtf=0.2, min_pass_lowest_mtf=0.2,
        use_50p=False, mtf_sample_count=252,
        mtf_patch_width=10) # patch width 10 for VGA
    self.assertEqual(success, True)
    self.assertAlmostEqual(tar_mtf.mtf, 0.2961126, delta=0.00001)
    self.assertAlmostEqual(tar_mtf.min_mtf, 0.2250828, delta=0.00001)

  def runTest(self):
    try:
      import cv      # pylint: disable=W0612,F0401
      import cv2     # pylint: disable=W0612,F0401
      import numpy   # pylint: disable=W0612,F0401
      import zbar    # pylint: disable=W0612,F0401
    except ImportError:
      print('Camera fixture unit test is skipped for missing OpenCV/numpy.')
      return

    self.TestIQ()
    print('IQ unit test has completed successfully.')


if __name__ == "__main__":
  unittest.main()
