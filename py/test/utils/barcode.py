# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Encapsulates QR Barcode scanner."""

try:
  import cv2 as cv
  import zbar
  import numpy as np
except ImportError:
  pass


def ScanQRCode(cv_image):
  """Encodes OpenCV image to common image format.

  Args:
    cv_image: OpenCV color image.

  Returns:
    List of scanned text.
  """
  width, height = cv_image.shape[1], cv_image.shape[0]
  raw_str = cv.cvtColor(cv_image, cv.COLOR_BGR2GRAY).astype(np.uint8).tostring()

  scanner = zbar.ImageScanner()
  scanner.set_config(zbar.Symbol.QRCODE, zbar.Config.ENABLE, 1)
  zbar_img = zbar.Image(width, height, 'Y800', raw_str)
  scanner.scan(zbar_img)

  return [symbol.data for symbol in zbar_img]
