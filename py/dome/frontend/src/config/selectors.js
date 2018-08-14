// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {NAME} from './constants';

export const localState = (state) => state.get(NAME);

export const isTFTPEnabled = (state) => localState(state).get('TFTPEnabled');
export const isConfigUpdating = (state) => localState(state).get('updating');