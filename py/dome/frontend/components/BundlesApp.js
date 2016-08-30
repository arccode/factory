// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import ContentAdd from 'material-ui/svg-icons/content/add';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import React from 'react';

import BundleList from './BundleList';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';
import UpdatingResourceForm from './UpdatingResourceForm';
import UploadingBundleForm from './UploadingBundleForm';

var BundlesApp = React.createClass({
  propTypes: {
    // TODO(littlecvr): there should be a better way to figure out the offset
    //                  automatically such as using float
    offset: React.PropTypes.number,
    openUploadingNewBundleForm: React.PropTypes.func.isRequired
  },

  render() {
    return (
      <div>
        <BundleList />

        <UploadingBundleForm />
        <UpdatingResourceForm />

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: this.props.offset,
            right: 24
          }}
          onTouchTap={this.props.openUploadingNewBundleForm}
        >
          <ContentAdd />
        </FloatingActionButton>
      </div>
    );
  }
});

function mapDispatchToProps(dispatch) {
  return {
    openUploadingNewBundleForm: () =>
        dispatch(DomeActions.openForm(FormNames.UPLOADING_BUNDLE_FORM))
  };
}

export default connect(null, mapDispatchToProps)(BundlesApp);
