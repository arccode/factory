// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {createSelector} from 'reselect';

import {NAME} from './constants';

export const localState = (state) => state.get(NAME);

export const getProjects = (state) => localState(state).get('projects');
export const getCurrentProject =
  (state) => localState(state).get('currentProject');
export const getCurrentProjectObject = createSelector(
    [getProjects, getCurrentProject],
    (projects, name) => projects.get(name, Immutable.Map()));
