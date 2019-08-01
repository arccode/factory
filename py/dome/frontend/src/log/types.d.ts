// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export interface LogFormData {
  logType: string;
  archiveSize: number;
  archiveUnit: string;
  startDate: string;
  endDate: string;
}

export interface downloadMessage {
  success: boolean;
  logPath: string;
}
