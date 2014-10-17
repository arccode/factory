# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

try:
  import cv2  # pylint: disable=F0401
except ImportError:
  pass

import numpy as np
import os
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import TimedUuid
from cros.factory.utils import file_utils

def EncodeCVImage(img, file_ext):
  """Encodes OpenCV image to common image format.

  Args:
    img: OpenCV image.
    file_ext: Image filename extension. Ex: '.bmp', '.jpg', etc.

  Returns:
    Encoded image data.
  """
  # TODO (jchuang): newer version of OpenCV has better imencode()
  # Python method.
  temp_fn = os.path.join(tempfile.gettempdir(), TimedUuid() + file_ext)
  try:
    cv2.imwrite(temp_fn, img)
    with open(temp_fn, 'rb') as f:
      return f.read()
  finally:
    file_utils.TryUnlink(temp_fn)

# Dimension padding/unpadding function for converting points matrices to
# the OpenCV format (channel-based).
def Pad(x):
  return np.expand_dims(x, axis=0)

def Unpad(x):
  return np.squeeze(x)

class Pod(object):
  """A POD (plain-old-data) object containing arbitrary fields."""
  def __init__(self, **args):
    self.__dict__.update(args)

  def __repr__(self):
    """Returns a representation of the object, including its properties."""
    return (self.__class__.__name__ + '(' +
            ', '.join('%s=%s' % (k, v) for k, v in sorted(self.__dict__.items())
                      if not k.startswith('_')) + ')')
