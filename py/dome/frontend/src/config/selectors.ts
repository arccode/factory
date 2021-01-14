// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {ConfigState} from './reducer';
import {Config} from './types';

export const localState = (state: RootState): ConfigState =>
  displayedState(state)[NAME];

export const getConfig =
  (state: RootState): Config => localState(state).config
export const isTftpEnabled =
  (state: RootState): boolean => localState(state).config.tftpEnabled;
export const isMcastEnabled =
  (state: RootState): boolean => localState(state).config.mcastEnabled;
export const isConfigUpdating =
  (state: RootState): boolean => localState(state).updating;
