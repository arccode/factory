// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

function getSortedTaskIDs(tasks) {
  // ImmutableJS accepts integers as keys, but JavaScript does not. To be
  // consistent we always store task IDs as strings. And when getting all task
  // IDs, a string to integer conversion is necessary to make the sorted result
  // correct. Common pitfalls here:
  const taskIDs = tasks.keySeq().toArray().map((x) => parseInt(x, 10));

  // JavaScript sorts everything alphabetically by default (even for a pure
  // integer array). We have to implement our own comparator.
  taskIDs.sort((a, b) => a - b);

  // convert back to strings to prevent bugs outside of this function because
  // taskIDs outside are all in strings.
  return taskIDs.map((x) => String(x));
}

export default {
  getSortedTaskIDs,
};
