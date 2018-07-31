// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {AppBarProps} from 'material-ui';
import AppBar from 'material-ui/AppBar';
import React from 'react';
import Measure from 'react-measure';

/* By default, AppBar does not stick to the top of the page, which means it is
 * possible to scroll it off the page. We need this workaround before
 * Material-UI has fixed it. See
 * https://github.com/callemall/material-ui/issues/1792
 */

interface FixedAppBarProps extends AppBarProps {
  onHeightChange: (height: number) => void;
}

const FixedAppBar: React.SFC<FixedAppBarProps> = ({
  onHeightChange,
  ...other
}) => (
  <div>
    <Measure onMeasure={(d) => onHeightChange(d.height)}>
      <AppBar
        {...other}
        style={{position: 'fixed', top: 0, left: 0}}
      />
    </Measure>
  </div>
);

export default FixedAppBar;
