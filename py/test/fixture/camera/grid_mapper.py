# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Import guard for OpenCV.
try:
    import cv
    import cv2
except ImportError:
    pass

import numpy as np

import utils

_GRID_REGISTRATION_MAX_ITER_NUM = 5
_GRID_REGISTRATION_MIN_MATCH_RATIO = 0.20


def _ComputePairL2Sq(xy1, xy2):
    '''Compute a pair-wise L2 square distance matrix.'''
    d0 = np.subtract.outer(xy1[:, 0], xy2[:, 0])
    d1 = np.subtract.outer(xy1[:, 1], xy2[:, 1])
    return d0 ** 2 + d1 ** 2


def _MatchPoints(src, dst, match_tol):
    '''Match two points sets based on the Euclidean distance.

    Args:
        src: Point set 1.
        dst: Point set 2.
        match_tol: Maximum acceptable distance between two points.

    Returns:
        1: The indexs that each point in src matches to in dst. None if a point
           can't find any match.
    '''
    n_match = src.shape[0]

    # We will work in the squared distance space.
    match_tol **= 2

    # Compute cost matrix.
    cost_mat = _ComputePairL2Sq(src, dst)

    # Assign points to nearest neighbors and return.
    m = np.empty(n_match, dtype=np.uint32)
    m.fill(n_match)
    taken = np.zeros(n_match, dtype=np.uint8)
    for i, row in enumerate(cost_mat):
        current = match_tol
        for j, value in enumerate(row):
            if not taken[j] and value <= current:
                m[i] = j
                current = value
        if m[i] == n_match:
            return None
        taken[j] = True
    return m


def Register(tar_four_corners, tar_corners, ref_four_corners, ref_corners,
             match_tol):
    '''Register two rectangular grid point sets.

    The function try to match two point sets with a prespective transformation.
    The four corners of both point grids must be supplied. The algorithm will
    iteratively re-match two point sets and estimate the corresponding
    homography matrix. It returns failure if it can't succeed in a few
    iterations or the iteration diverged.

    Args:
        tar_four_corners: Four corners of the target point grid.
        tar_corners: The target point grid.
        ref_four_corners: Four corners of the reference point grid.
        ref_corners: The reference point grid.
        match_tol: Maximum acceptable distance between two points.

    Returns:
        1: Succeed or not.
        2: The estimated homography matrix.
        3: The indexs that each point in the target image matches to in
           reference one. None if a point can't find any match.
    '''
    # Stupid dimension extension to fit the opencv interface.
    padded_tar_corners = utils.Pad(tar_corners)

    min_match_num = int(round(mapped.shape[0] *
                              _GRID_REGISTRATION_MIN_MATCH_RATIO))
    min_match_num = max(4, min_match_num)

    # Compute an initial homography.
    homography, _ = cv2.findHomography(tar_four_corners, ref_four_corners)

    # Iteratively register the point grid.
    for i in range(0, _GRID_REGISTRATION_MAX_ITER_NUM):
        # Map and match points.
        mapped = cv2.perspectiveTransform(padded_tar_corners, homography)
        mapped = utils.Unpad(mapped)
        matching = _MatchPoints(mapped, ref_corners, match_tol)

        # Check if all points can find a close enough match.
        if not matching:
            return False, None, None

        # Compute a new homography.
        homography, mask = cv2.findHomography(mapped,
                                              ref_corners[matching],
                                              method=cv.CV_LMEDS)

        # Check if all points fit the found homography or return failure
        # in case the iteration diverged (too few point fitted).
        if not homography or mask.sum() < min_match_num:
            return False, None, None
        if mask.all():
            return True, homography, matching

    return False, None, None
