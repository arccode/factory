# -*- coding: utf-8 -*-
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
import threading
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils

_IMAGE_ROOT = '/usr/local/factory/misc/'
_DEFAULT_IMAGE_FILE = 'display_images.tar.gz'
_IMAGE_DIR = 'images'
_STATION_IMAGE_DIR = 'station'
_DUT_IMAGE_DIR = 'dut'
_THUMB_HEIGHT = 40
_IMAGE_INFO_HEIGHT = 360

_HTML_DISPLAY = """
<div id="display_title"></div>
<div id="prompt"></div>
<hr>
<div id="thumb_images"></div>
<div id="image_info"></div>
<hr>
<div id="upload"></div>
"""

_CSS_DISPLAY = """
.display-table {
  margin-left: auto;
  margin-right: auto;
  width: 60%;
  height: 80%;
  position: relative;
  padding-top: 10%;
  border-collapse: collapse;
  border: 1px solid gray;}
"""

_PROMPT = test_ui.MakeLabel(
    'Press space to show each image on display<br>'
    'Press Enter to PASS after showing all images',
    u'按空白键来拨放影像在萤幕上<br>'
    u'拨放完所有影像后,压下Enter表示成功'
)


def GetUploadMsg(name, index, total):
  """Get Uploading message.

  Arg:
    name: filename for uploading.
    index: the current index of the file.
    total: total files for uploading.
  """
  return test_ui.MakeLabel('(%d/%d)Uploading images %s' % (index, total, name),
                           u'(%d/%d)正在上传图档 %s' % (index, total, name))


def GetThumbImageTableTag(paths):
  """Get the html tag for images' thumbnail.

  Arg:
    paths: paths for images.
  """
  # show all thumbs on a raw.
  tag = '<table class="display-table">'
  tag += '<tr>'
  for path in paths:
    tag += '<td>'
    tag += '<img src="%s" height="%d"/>' % (path, _THUMB_HEIGHT)
    tag += '</td>'
  tag += '</tr></table>'
  return tag


class DisplayImageTest(unittest.TestCase):
  """Tests the function of display by displaying images.

  Properties:
    _ui: test ui.
    _template: ui template handling html layout.
    _extract_dir: temp directory for keeping image files on the station.
    _station_image_paths: list of image paths for displaying on Station.
    _dut_temp_dir: temp directory for keeping image files on DUT.
    _dut_image_paths: list of image paths in DUT.
    _image_index: index of the image to be displayed.
    _uploaded_index: index of the latest uploaded image.
    _total_images: number of total images.
    _can_pass: check if operator checks all images.
  """
  ARGS = [
      Arg('title', tuple, 'Label Title of the test (en, zh)',
          ('Display', u'显示测试')),
      Arg('compressed_image_file', str, 'Compressed image file name.',
          default=_DEFAULT_IMAGE_FILE)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self._dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)

    self._ui.AppendCSS(_CSS_DISPLAY)
    self._template.SetState(_HTML_DISPLAY)
    self._ui.SetHTML(
        test_ui.MakeLabel(self.args.title[0], self.args.title[1]),
        id='display_title')
    self._ui.SetHTML(_PROMPT, id='prompt')
    self._dut_temp_dir = self._dut.temp.mktemp(True, '', 'display')
    self._image_index = -1
    self._uploaded_index = -1
    self._can_pass = False
    self.PrepareImages()

  def tearDown(self):
    self._dut.display.StopDisplayImage()
    process_utils.Spawn(['rm', '-rf', self._extract_dir],
                        check_call=True, log=True)
    self._dut.Call(['rm', '-rf', self._dut_temp_dir])

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    self._ui.BindKey(test_ui.SPACE_KEY, lambda _: self.OnSpacePressed())
    self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self.OnEnterPressed())
    self._ui.Run()

  def UploadImages(self, dut_image_filenames):
    """Upload images to DUT."""
    for i in xrange(self._total_images):
      basename = dut_image_filenames[i]
      # path in the station
      path = os.path.join(self._extract_dir, _DUT_IMAGE_DIR, basename)
      dut_path = self._dut_image_paths[i]
      self._ui.SetHTML(GetUploadMsg(basename, i + 1, self._total_images),
                       id='upload')
      self._dut.link.Push(path, dut_path)
      self._uploaded_index = i

  def PrepareImages(self):
    """Prepare image files on Station and DUT"""
    self._extract_dir = os.path.join(self._ui.GetStaticDirectoryPath(),
                                     _IMAGE_DIR)
    file_utils.ExtractFile(
        os.path.join(_IMAGE_ROOT, self.args.compressed_image_file),
        self._extract_dir)
    image_path_pattern = os.path.join(self._extract_dir, _DUT_IMAGE_DIR, '*')
    image_paths = sorted(glob.glob(image_path_pattern))
    dut_image_filenames = [os.path.basename(x) for x in image_paths]
    self._dut_image_paths = [self._dut.path.join(self._dut_temp_dir, x)
                             for x in dut_image_filenames]

    station_paths = glob.glob(os.path.join(self._extract_dir,
                                           _STATION_IMAGE_DIR, '*'))
    self._station_image_paths = [os.path.join(_IMAGE_DIR, _STATION_IMAGE_DIR,
                                              os.path.basename(x))
                                 for x in sorted(station_paths)]
    self._total_images = len(dut_image_filenames)
    # Because uploading images cost a lot of time, use another thread to do it.
    # Operator can test uploaded images in parallel.
    thread = threading.Thread(target=lambda:
                              self.UploadImages(dut_image_filenames))
    thread.start()

    tag = GetThumbImageTableTag(self._station_image_paths)
    self._ui.SetHTML(tag, id='thumb_images')

  def OnSpacePressed(self):
    """Display next image."""
    display_index = (self._image_index + 1) % self._total_images
    # Don't do display if the image is not uploaded.
    if display_index > self._uploaded_index:
      return

    # show the image on the chromebook to let operator know what will be shown
    # on the DUT.
    path = self._station_image_paths[display_index]
    tag = '%d:<img src="%s" height="%d"/>' % (display_index, path,
                                              _IMAGE_INFO_HEIGHT)
    self._ui.SetHTML(tag, id='image_info')
    # Display image on DUT.
    dut_path = self._dut_image_paths[display_index]
    logging.info('Display image index %d, image %s, dut path %s',
                 display_index, path, dut_path)
    self._dut.display.StopDisplayImage()
    self._dut.display.DisplayImage(dut_path)
    self._image_index = display_index

    if display_index == self._total_images - 1:
      self._can_pass = True

  def OnEnterPressed(self):
    """Passes the test."""
    if self._can_pass:
      self._ui.Pass()
