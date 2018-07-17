// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {JSONSchema6} from 'json-schema';

// TODO(pihsun): We can use some sort of JSON schema to TypeScript compiler to
// automatically generate this from Umpire JSON schema.
export type Service = any;

export interface ServiceMap {
  [name: string]: Service;
}

export type Schema = JSONSchema6;

export interface SchemaMap {
  [name: string]: Schema;
}
