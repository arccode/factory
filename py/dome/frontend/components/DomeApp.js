// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import React from 'react';

import WelcomePage from './WelcomePage';
import AppPage from './AppPage';

const DomeApp = props => (
  <div>
    {props.board === '' && <WelcomePage />}
    {props.board !== '' && <AppPage />}
  </div>
);

function mapStateToProps(state) {
  return {
    board: state.getIn(['dome', 'currentBoard'])
  };
}

export default connect(mapStateToProps, null)(DomeApp);
