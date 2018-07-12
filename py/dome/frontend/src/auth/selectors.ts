// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {NAME} from './constants';
import {AuthState} from './reducer';

export const localState = (state: RootState): AuthState => state[NAME];

export const isLoggedIn =
  (state: RootState): boolean => localState(state).isLoggedIn;
