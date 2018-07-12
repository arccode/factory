// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export const Enum = <T extends string>(items: T[]): {[K in T]: K} => {
  return items.reduce((object, item) => {
    object[item] = item;
    return object;
  }, Object.create(null));
};
