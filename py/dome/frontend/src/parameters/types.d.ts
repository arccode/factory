// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export interface UpdateParameterRequest {
  project: string;
  id: number | null;
  dirId: number | null;
  name: string;
  file: File;
}

export interface UpdateParameterFormPayload {
  id: number | null;
  dirId: number | null;
  name: string;
  multiple: boolean;
}

export interface UpdateParameterVersionRequest {
  id: number;
  name: string;
  usingVer: number;
}

export interface RenameRequest {
  id: number;
  name: string;
}

export interface Parameter {
  id: number;
  dirId: number | null;
  name: string;
  usingVer: number;
  revisions: string[];
}

export interface ParameterDirectory {
  id: number;
  parentId: number | null;
  name: string;
}

export interface CreateDirectoryRequest {
  name: string;
  parentId: number | null;
}
