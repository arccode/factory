// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {LogState} from './reducer';
import {
  ComponentState,
  DownloadStateMap,
  ExpansionMap,
  PileMap,
} from './types';

export const localState = (state: RootState): LogState =>
  displayedState(state)[NAME];

export const getDefaultDownloadDate =
  (state: RootState): string => {
  const defaultDate = localState(state).defaultDownloadDate;
  return defaultDate === '' ?
    new Date().toISOString().slice(0, 10) : defaultDate;
};

export const getExpansionMap =
  (state: RootState): ExpansionMap => localState(state).expanded;

export const getPiles =
  (state: RootState): PileMap =>
    localState(state).piles;

export const getOverallDownloadStateFromStateMap =
  (downloadStateMap: DownloadStateMap): ComponentState => {
    const downloadStates = Object.values(downloadStateMap);
    if (downloadStates.length === 0) {
      return 'WAITING';
    } else if (downloadStates.find((value) => value === 'PROCESSING')) {
      return 'PROCESSING';
    } else if (downloadStates.find((value) => value === 'FAILED')) {
      return 'FAILED';
    } else {
      return 'SUCCEEDED';
    }
};
