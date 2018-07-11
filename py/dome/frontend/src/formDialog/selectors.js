// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {NAME} from './constants';

export const localState = (state) => state[NAME];

export const isFormVisibleFactory = (name) =>
  (state) => localState(state).visibility[name] || false;

export const getFormPayloadFactory = (name) =>
  (state) => localState(state).payload[name] || {};
