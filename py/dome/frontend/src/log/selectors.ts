// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {LogState} from './reducer';

export const localState = (state: RootState): LogState =>
  displayedState(state)[NAME];

export const getDefaultDownloadDate =
  (state: RootState): string => {
  const defaultDate = localState(state).defaultDownloadDate;
  return defaultDate === '' ?
    new Date().toISOString().slice(0, 10) : defaultDate;
};
