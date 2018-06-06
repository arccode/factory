// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import FloatingActionButton from 'material-ui/FloatingActionButton';
import ContentAdd from 'material-ui/svg-icons/content/add';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import {openForm} from '../../formDialog/actions';
import {UPLOADING_BUNDLE_FORM} from '../constants';

import BundleList from './BundleList';
import UpdatingResourceForm from './UpdatingResourceForm';
import UploadingBundleForm from './UploadingBundleForm';

class BundlesApp extends React.Component {
  static propTypes = {
    // TODO(littlecvr): there should be a better way to figure out the offset
    //                  automatically such as using float
    offset: PropTypes.number,
    openUploadingNewBundleForm: PropTypes.func.isRequired,
  };

  render() {
    return (
      <>
        <BundleList />

        <UploadingBundleForm />
        <UpdatingResourceForm />

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: this.props.offset,
            right: 24,
          }}
          onClick={this.props.openUploadingNewBundleForm}
        >
          <ContentAdd />
        </FloatingActionButton>
      </>
    );
  }
}

function mapDispatchToProps(dispatch) {
  return {
    openUploadingNewBundleForm: () => (
      dispatch(openForm(UPLOADING_BUNDLE_FORM))
    ),
  };
}

export default connect(null, mapDispatchToProps)(BundlesApp);
