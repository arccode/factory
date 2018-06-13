// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {updateProject} from '@app/project/actions';

export const disableUmpire = (projectName) => (
  updateProject(projectName, {umpireEnabled: false})
);

export const enableUmpireWithSettings = (projectName, umpireSettings) => (
  updateProject(
      projectName,
      Object.assign({umpireEnabled: true}, umpireSettings))
);
