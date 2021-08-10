# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.external import cv2 as cv
from cros.factory.external import numpy as np

# different kinds of grids
GRID_SHAPES = [[40, 40], [20, 20], [10, 30], [30, 10]]
# MAX_GRID_SIZE is used to draw the approximate detection region on UI.
MAX_GRID_SIZE = [max(x for x, _ in GRID_SHAPES), max(y for _, y in GRID_SHAPES)]


class DetectCameraAssemblyIssue:
  """Detect the camera assembly issue by checking the luminance of an image.

  The boundary region of the image taken from badly assembled camera tends to be
  darker or having black edges. If the luminance value of the boundary region is
  lower than a predefined threshold, we consider the camera being badly
  assembled.
  """

  def __init__(self, cv_image, min_luminance_ratio=0.5):
    """Constructor of DetectCameraAssemblyIssue.

    Args:
      cv_image: OpenCV color image
      min_luminance_ratio: the minimum acceptable luminance of the boundary
                           region
    """
    self.cv_image = cv.cvtColor(cv_image, cv.COLOR_BGR2GRAY)
    self.cv_color_image = cv_image
    self.min_luminance_ratio = min_luminance_ratio

  def _AveragePooling(self, grid_height, grid_width):
    """Map N*M image to n*m grids by averaging the pixel values in the grids.
    """
    img_height, img_width = self.cv_image.shape

    # Calculate the ceiling of (img_width / grid_width)
    num_horizontal_grid = (img_width // grid_width) + (
        img_width % grid_width != 0)
    num_vertical_grid = (img_height // grid_height) + (
        img_height % grid_height != 0)

    # Calculate which pixel belongs to which grid
    grid_row_idx = np.arange(0, img_height) // grid_height
    grid_row_idx = np.clip(grid_row_idx, None, num_vertical_grid - 1)
    grid_col_idx = np.arange(0, img_width) // grid_width
    grid_col_idx = np.clip(grid_col_idx, None, num_horizontal_grid - 1)

    # We use bin count to calculate the sum of pixel values in each grid.
    # Moreover, since numpy.bincount only accept 1d index, we turn the 2d index
    # into 1d index.

    # Shape of two_d_row_idx, two_d_col_idx = (img_height, img_width)
    two_d_row_idx, two_d_col_idx = np.meshgrid(grid_col_idx, grid_row_idx)
    two_d_idx = two_d_row_idx + two_d_col_idx * num_horizontal_grid
    one_d_idx = two_d_idx.flatten()
    sum_grid_vals = np.bincount(one_d_idx, weights=self.cv_image.flatten())

    # Calculate the number of pixels in each grid
    one_d_ones_array = np.ones((img_height * img_width), dtype=int)
    num_pixels_each_grid = np.bincount(one_d_idx, weights=one_d_ones_array)

    avg_grid_vals = sum_grid_vals / num_pixels_each_grid
    avg_grid_vals = avg_grid_vals.reshape(num_vertical_grid,
                                          num_horizontal_grid)

    return avg_grid_vals

  def IsBoundaryRegionTooDark(self):
    """Check whether the luminance of the boundary grids are too low.

    We divide the image into different kinds of n*m grids and averaging the
    pixel value of each grid. If the pixel value of the boundary grids is lower
    than or equal to min_luminance_ratio multiplied by the brightest grid, which
    is the center grid, then the image is likely to contain black edges, and
    thus the camera is badly assembled. For instance, if the luminance value of
    the center grid is 150 and the min_luminance_ratio is 0.5, then boundary
    grids lower than or equal to 75 are rejected.

    Returns:
      A tuple of boolean, 2d array and a tuple
      boolean: The boundary is too dark or not
      2d array: n*m bool grids which represents each grid is too dark or not
      tuple: The width and height of each grid
    """
    for grid_height, grid_width in GRID_SHAPES:
      avg_grid_vals = self._AveragePooling(grid_height, grid_width)
      num_vertical_grid, num_horizontal_grid = avg_grid_vals.shape

      # We calculate the average pixel value of the center grid
      center_vertical_grid = num_vertical_grid // 2
      center_horizontal_grid = num_horizontal_grid // 2

      # Calculate the average grid values if grid num is even
      vertical_grid_start = center_vertical_grid - (num_vertical_grid % 2 == 0)
      horizontal_grid_start = center_horizontal_grid - (
          num_horizontal_grid % 2 == 0)
      center_grid_avg_val = 0
      num_grids = 0
      for i in range(vertical_grid_start, center_vertical_grid + 1):
        for j in range(horizontal_grid_start, center_horizontal_grid + 1):
          center_grid_avg_val += avg_grid_vals[i][j]
          num_grids += 1
      center_grid_avg_val //= num_grids

      min_luminance_value = self.min_luminance_ratio * center_grid_avg_val
      grid_is_too_dark = avg_grid_vals <= min_luminance_value
      # We mask out the center region since we only check if the boundary
      # region is too dark.
      grid_is_too_dark[1:-1, 1:-1] = False
      is_too_dark = np.any(grid_is_too_dark)
      if is_too_dark:
        return is_too_dark, grid_is_too_dark, (grid_width, grid_height)

    return False, None, None


def GetQRCodeDetectionRegion(img_height, img_width):
  """Calculate the detection region using the shape of the grid.

  Returns:
    The x, y coordinates, width and height of the detection region.
  """
  y_pos, x_pos = MAX_GRID_SIZE
  width = (img_width // 2) - x_pos
  height = img_height - y_pos * 2

  return x_pos, y_pos, width, height
