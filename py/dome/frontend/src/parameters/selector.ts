// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {ParameterState} from './reducer';
import {Parameter, ParameterDirectory} from './types';

export const localState = (state: RootState): ParameterState =>
  displayedState(state)[NAME];

export const getParameters =
  (state: RootState): Parameter[] => localState(state).files;

export const getParameterDirs =
  (state: RootState): ParameterDirectory[] => localState(state).dirs;
