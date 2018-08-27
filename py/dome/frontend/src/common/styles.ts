// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import grey from '@material-ui/core/colors/grey';
import {CSSProperties} from '@material-ui/core/styles/withStyles';

export const thinScrollBarX: CSSProperties = {
  overflowX: 'auto',
  '&::-webkit-scrollbar': {
    height: 6,
    backgroundColor: grey[300],
  },
  '&::-webkit-scrollbar-thumb': {
    backgroundColor: grey[500],
  },
};

export const thinScrollBarY: CSSProperties = {
  overflowY: 'auto',
  '&::-webkit-scrollbar': {
    width: 6,
    backgroundColor: grey[300],
  },
  '&::-webkit-scrollbar-thumb': {
    backgroundColor: grey[500],
  },
};
