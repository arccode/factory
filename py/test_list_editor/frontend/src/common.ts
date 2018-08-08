// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export interface FileSystemState {
  dirs: Array<{name: string, path: string, filelist: string[]}>;
  files: {[basename: string]: string};
}
