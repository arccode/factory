# -*- coding: utf-8; tab-width: 4; python-indent: 4 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Import guard for OpenCV.
try:
    import cv
    import cv2
except ImportError:
    pass

import itertools
import math
import numpy as np
import sys

import mtf_calculator
import grid_mapper

from camera_utils import Pod
from camera_utils import Pad
from multiprocessing import Pool

_CORNER_MAX_NUM = 1000000
_CORNER_QUALITY_RATIO = 0.05
_CORNER_MIN_DISTANCE_RATIO = 0.016

_EDGE_LINK_THRESHOLD = 2000
_EDGE_DETECT_THRESHOLD = 4000
_EDGE_MIN_SQUARE_SIZE_RATIO = 0.024

_POINT_MATCHING_MAX_TOLERANCE_RATIO = 0.020

_IMAGE_DEFAULT_MAX_SHIFT = 0.025
_IMAGE_DEFAULT_MAX_TILT = 1

_MTF_DEFAULT_MAX_CHECK_NUM = 308
_MTF_DEFAULT_PATCH_WIDTH = 20
_MTF_DEFAULT_CROP_RATIO = 0.25
_MTF_DEFAULT_CHECK_PASS_VALUE = 0.45
_MTF_DEFAULT_CHECK_PASS_VALUE_LOWEST = 0.10
_MTF_DEFAULT_THREAD_COUNT = 4

_SHADING_DOWNSAMPLE_RATIO = 0.20
_SHADING_BILATERAL_SPATIAL_SIGMA = 20
_SHADING_BILATERAL_RANGE_SIGMA = 0.15
_SHADING_DEFAULT_MAX_RESPONSE = 0.01
_SHADING_DEFAULT_MAX_TOLERANCE_RATIO = 0.15


class ReturnValue(Pod):
    pass


def _MTFComputeWrapper(args):
    '''Parallel MTF computation wrapper function.'''
    return mtf_calculator.Compute(*args)[0]


def _SqueezeCorners(corners):
    '''OpenCV returns corners in ndarray with dimension as [num_corners, 1, 2].
       We want to squeeze it to smaller dimension as [num_corners, 2]

    Args:
        corners: the corners as ndarray

    Returns:
        Squeezed ndarray without the redundant single-demensional entries at
        axis = 1
    '''
    # TODO(jchuang): it would be simplier and more general with newer numpy
    # (>1.7), which supports 'axis' parameter in np.squeeze().
    assert(len(corners.shape) == 3 and corners.shape[1] == 1 and
           corners.shape[2] == 2)
    if corners.shape[0] == 1:
        return corners[0]
    else:
        return np.squeeze(corners)


def _FindCornersOnConvexHull(hull):
    '''Find the four corners of a rectangular point grid.'''
    # Compute the inner angle of each point on the hull.
    hull_left = np.roll(hull, -1, axis=0)
    hull_right = np.roll(hull, 1, axis=0)

    hull_dl = hull_left - hull
    hull_dr = hull_right - hull

    angle = np.sum(hull_dl * hull_dr, axis=1)
    angle /= np.sum(hull_dl ** 2, axis=1) ** (1./2)
    angle /= np.sum(hull_dr ** 2, axis=1) ** (1./2)

    # Take the top four sharpest angle points and
    # arrange them in the same order as on the hull.
    corners = hull[np.sort(np.argsort(angle)[:-5:-1])]
    return corners


def _ComputeCosine(a, b):
    '''Compute the cosine value of the angle bewteen two vectors a and b.'''
    return np.sum(a * b) / math.sqrt(np.sum(a ** 2) * np.sum(b ** 2) + 1e-10)


def _ComputeShiftAndTilt(rect, img_size):
    '''Compute the shift and tilt values for a given rectangle in the form of
       its four corners.

    Args:
        rect: The four corners of the rectangle in the contour's order.
        img_size: The size of the whole image.

    Returns:
        The shift vector length.
        The tilt degrees.
        The shift vector.
    '''
    # Compute the shift.
    center = np.sum(rect, axis=0) / 4.0
    shift = center - np.array((img_size[1] - 1.0, img_size[0] - 1.0)) / 2.0
    shift_len = math.sqrt(np.sum(shift ** 2))

    # Compute the tilt (image rotation).
    va = (rect[1] - rect[0] + rect[2] - rect[3]) / 2.0
    vb = (rect[2] - rect[1] + rect[3] - rect[0]) / 2.0
    la = math.sqrt(np.sum(va ** 2))
    lb = math.sqrt(np.sum(vb ** 2))
    # Get the sign of the rotation angle by looking at the long side.
    sign = (np.sign(-va[1] * va[0]) if la > lb else np.sign(-vb[1] * vb[0]))
    if sign == 0:
        sign = 1
    da = np.max(np.abs(va)) / la
    db = np.max(np.abs(vb)) / lb
    return shift_len, sign * math.degrees(math.acos((da + db) / 2.0)), shift


def _CheckSquareness(contour, min_square_area):
    '''Check the squareness of a contour.'''
    if len(contour) != 4:
        return False

    # Filter out noise squares.
    if cv2.contourArea(Pad(contour)) < min_square_area:
        return False

    # Check convexity.
    if not cv2.isContourConvex(Pad(contour)):
        return False

    min_angle = 0
    for i in range(0, 4):
        # Find the minimum inner angle.
        dl = contour[i] - contour[i-1]
        dr = contour[i-2] - contour[i-1]
        angle = _ComputeCosine(dl, dr)

        ac = abs(angle)
        if ac > min_angle:
            min_angle = ac

    # If the absolute value of cosines of all angles are small, then all angles
    # are ~90 degree -> implies a square.
    if min_angle > 0.3:
        return False
    return True


def _ExtractEdgeSegments(edge_map, min_square_size_ratio):
    '''Extract robust edges of squares from a binary edge map.'''
    diag_len = math.sqrt(edge_map.shape[0] ** 2 + edge_map.shape[1] ** 2)
    min_square_area = int(round(diag_len * min_square_size_ratio)) ** 2

    # Dilate the output from Canny to fix broken edge segments.
    edge_map = edge_map.copy()
    cv.Dilate(edge_map, edge_map, None, 1)

    # Find contours of the binary edge map.
    squares = []
    storage = cv.CreateMemStorage()
    contours = cv.FindContours(edge_map, storage, cv.CV_RETR_TREE,
                               cv.CV_CHAIN_APPROX_SIMPLE)

    # Check if each contour is a square.
    storage = cv.CreateMemStorage()
    while contours:
        # Approximate contour with an accuracy proportional to the contour
        # perimeter length.
        arc_len = cv.ArcLength(contours)
        polygon = cv.ApproxPoly(contours, storage, cv.CV_POLY_APPROX_DP,
                                arc_len * 0.02)
        polygon = np.array(polygon, dtype=np.float32)

        # If the contour passes the squareness check, add it to the list.
        if _CheckSquareness(polygon, min_square_area):
            sq_edges = np.hstack((polygon, np.roll(polygon, -1, axis=0)))
            for t in range(4):
                squares.append(sq_edges[t])

        contours = contours.h_next()

    return np.array(squares, dtype=np.float32)


def _StratifiedSample2D(xys, n, dims=None, strict=False):
    '''Do stratified random sampling on a 2D point set.

    The algorithm will try to spread the samples around the plane.

    Args:
        n: Sample count requested.
        dims: The x-y plane size that is used to normalize the coordinates.
        strict: Should we fall back to the pure random sampling on failure.

    Returns:
        A list of indexes of sampled points.
    '''
    if not dims:
        dims = np.array([1, 1.0])

    # Place the points onto the grid in a random order.
    ln = xys.shape[0]
    perm = np.random.permutation(ln)
    grid_size = math.ceil(math.sqrt(n))
    taken = np.zeros((grid_size, grid_size), dtype=np.bool)
    result = []
    for t in perm:
        # Normalize the coordinates to [0, 1).
        gx = int(xys[t, 0] * grid_size / dims[1])
        gy = int(xys[t, 1] * grid_size / dims[0])
        if not taken[gy, gx]:
            taken[gy, gx] = True
            result.append(t)
            if len(result) == n:
                break

    # Fall back to the pure random sampling on failure.
    if len(result) != n:
        if not strict:
            return perm[0:n]
        return None
    return np.array(result)


def PrepareTest(pat_file):
    '''Extract information from the reference test pattern.

    The data will be used in the actual test as the ground truth.
    '''
    ret = ReturnValue()

    # Locate corners.
    pat = cv2.imread(pat_file, cv.CV_LOAD_IMAGE_GRAYSCALE)
    diag_len = math.sqrt(pat.shape[0] ** 2 + pat.shape[1] ** 2)
    min_corner_dist = diag_len * _CORNER_MIN_DISTANCE_RATIO

    ret.corners = _SqueezeCorners(
        cv2.goodFeaturesToTrack(pat, _CORNER_MAX_NUM, _CORNER_QUALITY_RATIO,
                                min_corner_dist))

    ret.pmatch_tol = diag_len * _POINT_MATCHING_MAX_TOLERANCE_RATIO

    # Locate four corners of the corner grid.
    hull = _SqueezeCorners(cv2.convexHull(Pad(ret.corners)))
    ret.four_corners = _FindCornersOnConvexHull(hull)

    # Locate edges.
    edge_map = cv2.Canny(pat, _EDGE_LINK_THRESHOLD, _EDGE_DETECT_THRESHOLD,
                         apertureSize=5)

    ret.edges = _ExtractEdgeSegments(edge_map, _EDGE_MIN_SQUARE_SIZE_RATIO)
    return ret


def CheckLensShading(sample, check_low_freq=True,
                     max_response=_SHADING_DEFAULT_MAX_RESPONSE,
                     max_shading_ratio=_SHADING_DEFAULT_MAX_TOLERANCE_RATIO):
    '''Check if lens shading is present.

    Args:
        sample: The test target image. It needs to be single-channel.
        check_low_freq: Check low frequency variation or not. The low frequency
                        is very sensitive to uneven illumination so one may want
                        to turn it off when a fixture is not available.
        max_response: Maximum acceptable response of low frequency variation.
        max_shading_ratio: Maximum acceptable shading ratio value of boundary
                           pixels.

    Returns:
        1: Pass or Fail.
        2: A structure contains the response value and the error message in case
           the test failed.
    '''
    ret = ReturnValue(msg=None)

    # Downsample for speed.
    ratio = _SHADING_DOWNSAMPLE_RATIO
    img = cv2.resize(sample, None, fx=ratio, fy=ratio,
                     interpolation=cv2.INTER_AREA)
    img = img.astype(np.float32)

    # Method 1 - Low-frequency variation check:
    ret.check_low_freq = False
    if check_low_freq:
        ret.check_low_freq = True
        # Homomorphic filtering.
        ilog = np.log(0.001 + img)
        # Substract a bilateral smoothed version.
        ismooth = cv2.bilateralFilter(ilog,
                                      _SHADING_BILATERAL_SPATIAL_SIGMA * 3,
                                      _SHADING_BILATERAL_RANGE_SIGMA,
                                      _SHADING_BILATERAL_SPATIAL_SIGMA,
                                      borderType=cv2.BORDER_REFLECT)
        ihigh = ilog - ismooth

        # Check if there are significant response.
        # The response is computed as the 95th pencentile minus the median.
        ihsorted = np.sort(ihigh, axis=None)
        N = ihsorted.shape[0]
        peak_to_med = ihsorted[int(0.95 * N)] - ihsorted[int(0.5 * N)]
        ret.response = peak_to_med
        if peak_to_med > max_response:
            ret.msg = 'Found significant low-frequency variation.'
            return False, ret

    # Method 2 - Boundary scan:
    # Get the mean of top 5 percent pixels.
    ihsorted = np.sort(img, axis=None)
    mtop = np.mean(ihsorted[int(0.90 * ihsorted.shape[0]):
                            int(0.95 * ihsorted.shape[0])])
    pass_value = mtop * (1.0 - max_shading_ratio)

    # Check if any pixel on the boundary is lower than the threshold.
    # A little smoothing to deal with the possible noise.
    k_size = (7, 7)
    edge1 = cv2.blur(img[0, :], k_size)
    edge2 = cv2.blur(img[-1, :], k_size)
    edge3 = cv2.blur(img[:, 0], k_size)
    edge4 = cv2.blur(img[:, -1], k_size)
    lowest_value = min(np.min(edge1),
                       np.min(edge2),
                       np.min(edge3),
                       np.min(edge4))
    ret.lowest_ratio = lowest_value / mtop

    if lowest_value < pass_value:
        ret.msg = 'Found dark pixels on the boundary.'
        return False, ret
    else:
        ret.msg = None
        return True, ret


def CheckVisualCorrectness(
    sample, ref_data, register_grid=False, corner_only=False,
    min_corner_quality_ratio=_CORNER_QUALITY_RATIO,
    min_square_size_ratio=_EDGE_MIN_SQUARE_SIZE_RATIO,
    min_corner_distance_ratio=_CORNER_MIN_DISTANCE_RATIO,
    max_image_shift=_IMAGE_DEFAULT_MAX_SHIFT,
    max_image_tilt=_IMAGE_DEFAULT_MAX_TILT):
    '''Check if the test pattern is present.

    Args:
        sample: The test target image. It needs to be single-channel.
        ref_data: A struct that contains information extracted from the
                  reference pattern using PrepareTest.
        register_grid: Check if the point grid can be matched to the reference
                       one, i.e. whether they are of the same type.
        corner_only: Check only the corners (skip the edges).
        min_corner_quality_ratio: Minimum acceptable relative corner quality
                                  difference.
        min_square_size_ratio: Minimum allowed square edge length in relative
                               to the image diagonal length.
        min_corner_distance_ratio: Minimum allowed corner distance in relative
                                   to the image diagonal length.
        max_image_shift: Maximum allowed image center shift in relative to the
                         image diagonal length.
        max_image_tilt: Maximum allowed image tilt amount in degrees.

    Returns:
        1: Pass or Fail.
        2: A structure contains the found corners and edges and the error
           message in case the test failed.
    '''
    ret = ReturnValue(msg=None)

    # CHECK 1:
    # a) See if all corners are present with reasonable strength.
    edge_map = cv2.Canny(sample, _EDGE_LINK_THRESHOLD, _EDGE_DETECT_THRESHOLD,
                         apertureSize=5)
    dilator = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edge_mask = cv2.dilate(edge_map, dilator)

    diag_len = math.sqrt(sample.shape[0] ** 2 + sample.shape[1] ** 2)
    min_corner_dist = diag_len * min_corner_distance_ratio

    sample_corners = cv2.goodFeaturesToTrack(sample, ref_data.corners.shape[0],
                                             min_corner_quality_ratio,
                                             min_corner_dist, mask=edge_mask)
    if sample_corners is None:
        ret.msg = "Can't find strong corners."
        return False, ret

    sample_corners = _SqueezeCorners(sample_corners)
    ret.sample_corners = sample_corners

    # b) Check if we got the same amount of corners as the reference.
    if sample_corners.shape[0] != ref_data.corners.shape[0]:
        ret.msg = "Can't find the same amount of corners."
        return False, ret

    # Find the 4 corners of the square grid.
    hull = _SqueezeCorners(cv2.convexHull(Pad(sample_corners)))
    if hull.shape[0] < 4:
        ret.msg = "All the corners are co-linear."
        return False, ret
    ret.four_corners = _FindCornersOnConvexHull(hull)

    # c) Check if the image shift and tilt amount are within the spec.
    shift_len, ret.tilt, ret.v_shift = _ComputeShiftAndTilt(ret.four_corners,
                                                            sample.shape)
    ret.shift = shift_len / diag_len
    if ret.shift > max_image_shift:
        ret.msg = 'The image shift is too large.'
        return False, ret
    if abs(ret.tilt) > max_image_tilt:
        ret.msg = 'The image tilt is too large.'
        return False, ret
    # TODO(sheckylin) Refine points locations.

    # Perform point grid registration if requested. This can confirm that the
    # desired test pattern is correctly found (i.e. not fooled by some other
    # stuff) and also that the geometric distortion is small. However, we
    # choose to skip it by default due to the heavy computation demands.
    # TODO(sheckylin) Enable it after the C++ registration module is done.
    ret.register_grid = False
    if register_grid:
        ret.register_grid = True

        # There are 4 possible mappings of the 4 corners between the reference
        # and the sample due to rotation because we can't tell the starting
        # point of the convex hull on the rectangle grid.
        match = False
        for i in range(0,4):
            success, homography, _ = grid_mapper.Register(
                four_corners, sample_corners, ref_data.four_corners,
                ref_data.corners, ref_data.pmatch_tol)
            if success:
                match = True
                break

            four_corners = np.roll(four_corners, 1, axis=0)

        # CHECK 2:
        # Check if all corners are successfully mapped.
        if not match:
            ret.msg = "Can't match the sample to the reference."
            return False, ret
        ret.homography = homography

    if corner_only:
        return True, ret

    # Find squares on the edge map.
    edges = _ExtractEdgeSegments(edge_map, min_square_size_ratio)

    # CHECK 3:
    # Check if we can find the same amount of edges on the target.
    ret.edges = edges
    if edges.shape[0] != ref_data.edges.shape[0]:
        ret.msg = "Can't find the same amount of squares/edges."
        return False, ret
    return True, ret


def CheckSharpness(sample, edges,
                   min_pass_mtf=_MTF_DEFAULT_CHECK_PASS_VALUE,
                   min_pass_lowest_mtf=_MTF_DEFAULT_CHECK_PASS_VALUE_LOWEST,
                   mtf_sample_count=_MTF_DEFAULT_MAX_CHECK_NUM,
                   mtf_patch_width=_MTF_DEFAULT_PATCH_WIDTH,
                   mtf_crop_ratio=_MTF_DEFAULT_CROP_RATIO,
                   use_50p=True,
                   n_thread=_MTF_DEFAULT_THREAD_COUNT):
    '''Check if the captured image is sharp.

    Args:
        sample: The test target image. It needs to be single-channel.
        edges: A list of edges on the test image. Should be extracted with
               CheckVisualCorrectness.
        min_pass_mtf: Minimum acceptable (median) MTF value.
        min_pass_lowest_mtf: Minimum acceptable lowest MTF value.
        mtf_sample_count: How many edges we are going to compute MTF values.
        mtf_patch_width: The desired margin on the both side of an edge. Larger
                         margins provides more precise MTF values.
        mtf_crop_ratio: How much we want to truncate at the beginning and the
                        end of the edge. Lower value (less truncation) better
                        reduces the MTF value variations between each test.
        use_50p: Compute whether the MTF50P value or the MTF50 value.
        n_thread: Number of threads to use to compute MTF values.

    Returns:
        1: Pass or Fail.
        2: A structure contains the median MTF value (MTF50P) and the error
           message in case the test failed.
    '''
    ret = ReturnValue(msg=None)

    if (mtf_sample_count <= 0 or mtf_patch_width <= 0 or mtf_crop_ratio < 0 or
        mtf_crop_ratio > 1 or edges is None):
        ret.msg = 'Input values are invalid.'
        return False, ret
    line_start = edges[:, [0, 1]]
    line_end = edges[:, [2, 3]]
    ln = line_start.shape[0]

    # Compute MTF for some edges.
    # Random sample a few edges to work on.
    n_check = min(ln, mtf_sample_count)
    mids = (line_start + line_end) / 2
    mids = mids - np.amin(mids, axis=0)
    new_dim = np.amax(mids, axis=0) + 1
    perm = _StratifiedSample2D(mids, n_check, tuple([new_dim[1], new_dim[0]]))

    # Multi-threading to speed up the computation.
    if n_thread > 1:
        pool = Pool(processes=min(n_thread, n_check))
        mtfs = pool.map(_MTFComputeWrapper, itertools.izip(
            itertools.repeat(sample), line_start[perm], line_end[perm],
            itertools.repeat(mtf_patch_width), itertools.repeat(mtf_crop_ratio),
            itertools.repeat(use_50p)))
        pool.close()
        pool.join()
    else:
        mtfs = [mtf_calculator.Compute(sample, line_start[t], line_end[t],
                                       mtf_patch_width, mtf_crop_ratio,
                                       use_50p)[0] for t in perm]

    # CHECK 1:
    # Check if the median of MTF values pass the threshold.
    ret.perm = perm
    ret.mtfs = np.array(mtfs)
    ret.mtf = np.median(ret.mtfs)
    if  ret.mtf < min_pass_mtf:
        ret.msg = 'The MTF values are too low.'
        return False, ret

    # CHECK 2:
    # Check if the minimum of MTF values pass the threshold.
    ret.min_mtf = np.amin(ret.mtfs)
    if  ret.min_mtf < min_pass_lowest_mtf:
        ret.msg = 'The min MTF value is too low.'
        return False, ret
    return True, ret
