# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Encapsulates QR Barcode scanner."""

try:
  import cv
  import cv2
  import zbar
  import numpy as np
except ImportError:
  pass


def ScanQRCode(cv_img):
  """Encodes OpenCV image to common image format.

  Args:
    cv_img: OpenCV color image.

  Returns:
    List of scanned text.
  """
  width, height = cv_img.shape[1], cv_img.shape[0]
  raw_str = cv2.cvtColor(cv_img, cv.CV_BGR2GRAY).astype(np.uint8).tostring()

  scanner = zbar.ImageScanner()
  scanner.set_config(zbar.Symbol.QRCODE, zbar.Config.ENABLE, 1)
  zbar_img = zbar.Image(width, height, 'Y800', raw_str)
  scanner.scan(zbar_img)

  return [symbol.data for symbol in zbar_img]
