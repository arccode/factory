// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import project from '@app/project';

export const disableUmpire = (projectName) => (
  project.actions.updateProject(projectName, {umpireEnabled: false})
);

export const enableUmpireWithSettings = (projectName, umpireSettings) => (
  project.actions.updateProject(
      projectName,
      {umpireEnabled: true, ...umpireSettings})
);
