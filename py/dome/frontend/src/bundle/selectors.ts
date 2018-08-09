// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {NAME} from './constants';
import {BundleState} from './reducer';
import {Bundle} from './types';

export const localState = (state: RootState): BundleState => state[NAME];

export const getBundles =
  (state: RootState): Bundle[] => localState(state).entries;
export const getExpandedMap =
  (state: RootState): {[name: string]: boolean} => localState(state).expanded;