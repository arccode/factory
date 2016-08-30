// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* By default, AppBar does not stick to the top of the page, which means it is
 * possible to scroll it off the page. We need this workaround before
 * Material-UI has fixed it. See
 * https://github.com/callemall/material-ui/issues/1792
 */

import AppBar from 'material-ui/AppBar';
import React from 'react';

const FixedAppBar = React.createClass({
  getInitialState() {
    return {
      height: 0
    };
  },

  componentDidMount() {
    // TODO(littlecvr): should not use setState() in componentDidMount()
    this.setState({height: this.appBar.context.muiTheme.appBar.height});
  },

  render() {
    return (
      <div>
        <AppBar
          {...this.props}
          ref={c => this.appBar = c}
          style={{position: 'fixed', top: 0, left: 0}}
        />
        <div style={{height: this.state.height}}></div>
      </div>
    );
  }
});

export default FixedAppBar;
