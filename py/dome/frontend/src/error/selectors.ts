// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {ErrorState} from './reducer';

export const localState = (state: RootState): ErrorState =>
  displayedState(state)[NAME];

export const isErrorDialogShown =
  (state: RootState): boolean => localState(state).show;
export const getErrorMessage =
  (state: RootState): string => localState(state).message;
