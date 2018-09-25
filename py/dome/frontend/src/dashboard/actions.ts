// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import project from '@app/project';
import {UmpireSetting} from '@app/project/types';

export const disableUmpire = (projectName: string) => (
  project.actions.updateProject(
    projectName,
    {umpireEnabled: false},
    `Disable Umpire for project "${projectName}"`)
);

export const enableUmpireWithSettings =
  (projectName: string, umpireSettings: Partial<UmpireSetting>) => (
    project.actions.updateProject(
      projectName,
      {umpireEnabled: true, ...umpireSettings},
      `Enable Umpire for project "${projectName}"`)
  );
