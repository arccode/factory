// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export interface UpdateResourceFormPayload {
  bundleName: string;
  resourceKey: string;
  resourceType: string;
}

export interface UpdateResourceRequestPayload {
  project: string;
  name: string;
  newName: string;
  note: string;
  resources: {
    [resourceType: string]: {
      type: string;
      file: File;
    };
  };
}

export interface UploadBundleRequestPayload {
  project: string;
  name: string;
  note: string;
  bundleFile: File;
}

export interface Resource {
  type: string;
  version: string;
  hash: string;
}

export interface ResourceMap {
  [type: string]: Resource;
}

export interface Bundle {
  name: string;
  note: string;
  active: boolean;
  resources: ResourceMap;
}

export interface DeletedResources {
  files: string[];
  size: number;
}