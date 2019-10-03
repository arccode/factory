# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the function of display.

The test will display images on the display.
It will extract image files from factory/misc/display_images.tar.gz by default.
User can add new xx.tar.gz in the private overlay.
The display order is based on the sorted file name.

Two directories, dut/ and station/, are required in the image archive xx.tar.gz.
For each image to be tested, two images with same file name are required in each
directory, but we can use different extension name depending on the file format.
The image under dut/ is for displaying on DUT. The image under station/ is for
providing information to operators.
e.g.
dut/abc.ppm and station/abc.bmp
"""

import glob
import logging
import os

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils

_IMAGE_ROOT = '/usr/local/factory/misc/'
_DEFAULT_IMAGE_FILE = 'display_images.tar.gz'
_IMAGE_DIR = 'images'
_STATION_IMAGE_DIR = 'station'
_DUT_IMAGE_DIR = 'dut'


class DisplayImageTest(test_case.TestCase):
  """Tests the function of display by displaying images.

  Properties:
    _extract_dir: temp directory for keeping image files on the station.
    _station_image_urls: list of image paths for displaying on Station.
    _dut_temp_dir: temp directory for keeping image files on DUT.
    _image_index: index of the image to be displayed.
    _uploaded_index: index of the latest uploaded image.
    _total_images: number of total images.
    _can_pass: check if operator checks all images.
  """
  ARGS = [
      i18n_arg_utils.I18nArg(
          'title', 'Label Title of the test', default=_('Display Test')),
      Arg('compressed_image_file', str, 'Compressed image file name.',
          default=_DEFAULT_IMAGE_FILE)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self._dut = device_utils.CreateDUTInterface()

    self.ui.SetHTML(self.args.title, id='display-title')
    self._dut_temp_dir = self._dut.temp.mktemp(True, '', 'display')
    self._image_index = -1
    self._uploaded_index = -1
    self._can_pass = False

    self._extract_dir = os.path.join(self.ui.GetStaticDirectoryPath(),
                                     _IMAGE_DIR)
    file_utils.ExtractFile(
        os.path.join(_IMAGE_ROOT, self.args.compressed_image_file),
        self._extract_dir)

    image_paths = sorted(
        glob.glob(os.path.join(self._extract_dir, _DUT_IMAGE_DIR, '*')))
    self._dut_image_paths = [
        self._dut.path.join(self._dut_temp_dir, os.path.basename(x))
        for x in image_paths
    ]

    station_paths = sorted(
        glob.glob(os.path.join(self._extract_dir, _STATION_IMAGE_DIR, '*')))
    self._station_image_urls = [
        os.path.join(_IMAGE_DIR, _STATION_IMAGE_DIR, os.path.basename(x))
        for x in station_paths
    ]

    self.assertEqual(
        len(image_paths),
        len(station_paths),
        'There should be same number of images in dut and station folders.')

    # Because uploading images cost a lot of time, use another thread to do it.
    # Operator can test uploaded images in parallel.
    process_utils.StartDaemonThread(
        target=self.UploadImages, args=(station_paths, ))

    images = ''.join('<img src="%s" class="image-thumb">' % path
                     for path in self._station_image_urls)
    self.ui.SetHTML(images, id='display-table')

  def tearDown(self):
    self._dut.display.StopDisplayImage()
    process_utils.Spawn(['rm', '-rf', self._extract_dir],
                        check_call=True, log=True)
    self._dut.Call(['rm', '-rf', self._dut_temp_dir])

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    while True:
      pressed_key = self.ui.WaitKeysOnce([test_ui.SPACE_KEY, test_ui.ENTER_KEY])
      if pressed_key == test_ui.SPACE_KEY:
        self.OnSpacePressed()
      elif pressed_key == test_ui.ENTER_KEY:
        if self._can_pass:
          break

  def UploadImages(self, image_paths):
    """Upload images to DUT."""
    for i, (station_path, dut_path) in enumerate(zip(image_paths,
                                                     self._dut_image_paths)):
      name = os.path.basename(station_path)
      self.ui.SetHTML(
          _('({index}/{total}) Uploading images {name}',
            index=i + 1,
            total=len(image_paths),
            name=name),
          id='upload')
      self._dut.link.Push(station_path, dut_path)
      self._uploaded_index = i
    self.ui.SetHTML(_('All images uploaded.'), id='upload')

  def OnSpacePressed(self):
    """Display next image."""
    display_index = (self._image_index + 1) % len(self._station_image_urls)
    # Don't do display if the image is not uploaded.
    if display_index > self._uploaded_index:
      return

    # show the image on the chromebook to let operator know what will be shown
    # on the DUT.
    path = self._station_image_urls[display_index]
    tag = '%d: <img src="%s" class="image-info">' % (display_index, path)
    self.ui.SetHTML(tag, id='display-image-info')
    # Display image on DUT.
    dut_path = self._dut_image_paths[display_index]
    logging.info('Display image index %d, image %s, dut path %s',
                 display_index, path, dut_path)
    self._dut.display.StopDisplayImage()
    self._dut.display.DisplayImage(dut_path)
    self._image_index = display_index

    if display_index == len(self._station_image_urls) - 1:
      self._can_pass = True
