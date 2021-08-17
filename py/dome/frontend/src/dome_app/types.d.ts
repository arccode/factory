// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export type AppName =
  'PROJECTS_APP' |
  'BUNDLES_APP' |
  'CONFIG_APP' |
  'DASHBOARD_APP' |
  'PARAMETER_APP' |
  'LOG_APP' |
  'SYNC_STATUS_APP';

export interface DomeInfo {
  dockerImageGithash: string;
  dockerImageIslocal: boolean;
  dockerImageTimestamp: string;
  isDevServer: boolean;
}
