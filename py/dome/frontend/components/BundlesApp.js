// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import ContentAdd from 'material-ui/svg-icons/content/add';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import Immutable from 'immutable';
import React from 'react';

import Actions from '../actions/bundles';
import BundleList from './BundleList';
import FormNames from '../constants/FormNames';
import UpdatingResourceForm from './UpdatingResourceForm';
import UploadingBundleForm from './UploadingBundleForm';

var BundlesApp = React.createClass({
  propTypes: {
    openUploadingNewBundleForm: React.PropTypes.func.isRequired
  },

  render: function() {
    const {openUploadingNewBundleForm} = this.props;

    return (
      <div>
        <BundleList />

        <UploadingBundleForm />
        <UpdatingResourceForm />

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24
          }}
          onTouchTap={openUploadingNewBundleForm}
        >
          <ContentAdd />
        </FloatingActionButton>
      </div>
    );
  }
});

function mapDispatchToProps(dispatch) {
  return {
    openUploadingNewBundleForm:
        () => dispatch(Actions.openForm(FormNames.UPLOADING_BUNDLE_FORM))
  };
}

export default connect(null, mapDispatchToProps)(BundlesApp);
