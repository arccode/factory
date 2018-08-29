// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {DomeAppState} from './reducer';
import {AppName, DomeInfo} from './types';

export const localState = (state: RootState): DomeAppState =>
  displayedState(state)[NAME];

export const getCurrentApp =
  (state: RootState): AppName => localState(state).currentApp;

export const getDomeInfo =
  (state: RootState): DomeInfo | null => localState(state).domeInfo;
