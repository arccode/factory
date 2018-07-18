// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import {AppName} from './types';

export const switchApp = createAction('SWITCH_APP', (resolve) =>
  (nextApp: AppName) => resolve({nextApp}));

export const basicActions = {switchApp};
