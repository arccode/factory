// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {FormDialogState} from './reducer';
import {FormNames} from './types';

export const localState = (state: RootState): FormDialogState =>
  displayedState(state)[NAME];

export const isFormVisibleFactory = (name: FormNames) =>
  (state: RootState): boolean => localState(state).visibility[name] || false;

export const getFormPayloadFactory = <K extends FormNames>(name: K) =>
  (state: RootState) => localState(state).payload[name] || {};
