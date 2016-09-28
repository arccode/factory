// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* By default, AppBar does not stick to the top of the page, which means it is
 * possible to scroll it off the page. We need this workaround before
 * Material-UI has fixed it. See
 * https://github.com/callemall/material-ui/issues/1792
 */

import AppBar from 'material-ui/AppBar';
import Measure from 'react-measure';
import React from 'react';

const FixedAppBar = React.createClass({
  propTypes: {
    // callback when the height of the AppBar changes, signature: (height)
    onHeightChange: React.PropTypes.func
  },

  handleHeightChange(height) {
    this.setState({height});
    if ('onHeightChange' in this.props) {
      this.props.onHeightChange(height);
    }
  },

  getInitialState() {
    return {
      height: 0
    };
  },

  render() {
    const {onHeightChange: unused, ...other} = this.props;

    return (
      <div>
        <Measure onMeasure={d => this.handleHeightChange(d.height)}>
          <AppBar
            {...other}
            style={{position: 'fixed', top: 0, left: 0}}
          />
        </Measure>
        <div style={{height: this.state.height}}></div>
      </div>
    );
  }
});

export default FixedAppBar;
