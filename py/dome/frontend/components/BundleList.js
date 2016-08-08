// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import React from 'react';
import {connect} from 'react-redux';

import Actions from '../actions/bundles';
import Bundle from './Bundle';

var BundleList = React.createClass({
  propTypes: {
    bundles: React.PropTypes.instanceOf(Immutable.List).isRequired,
    handleRefresh: React.PropTypes.func.isRequired
  },

  componentDidMount() {
    this.props.handleRefresh();
  },

  render() {
    const {bundles} = this.props;

    return (
      <div>
        {bundles.map(bundle => {
          return <Bundle key={bundle.get('name')} bundle={bundle} />;
        }, this)}
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    bundles: state.getIn(['bundles', 'entries'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    handleRefresh: () => dispatch(Actions.fetchBundles())
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(BundleList);
