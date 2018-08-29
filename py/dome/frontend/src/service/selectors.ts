// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {ServiceState} from './reducer';
import {SchemaMap, ServiceMap} from './types';

export const localState = (state: RootState): ServiceState =>
  displayedState(state)[NAME];

export const getServices =
  (state: RootState): ServiceMap => localState(state).services;
export const getServiceSchemata =
  (state: RootState): SchemaMap => localState(state).schemata;
