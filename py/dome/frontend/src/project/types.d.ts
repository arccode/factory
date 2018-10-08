// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export interface UmpireSetting {
  umpireEnabled: boolean;
  umpirePort: number | null;
  netbootBundle: string | null;
}

export interface UmpireServerResponse {
  name: string;
  umpireEnabled: boolean;
  umpirePort: number | null;
  netbootBundle: string | null;
  hasExistingUmpire: boolean;
}

export interface Project extends UmpireSetting, UmpireServerResponse {
  umpireReady: boolean;
}

export interface ProjectMap {
  [name: string]: Project;
}
