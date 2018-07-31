// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import FloatingActionButton from 'material-ui/FloatingActionButton';
import ContentAdd from 'material-ui/svg-icons/content/add';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {UPLOAD_BUNDLE_FORM} from '../constants';

import BundleList from './bundle_list';
import UpdateResourceForm from './update_resource_form';
import UploadBundleForm from './upload_bundle_form';

interface BundlesAppProps {
  // TODO(littlecvr): there should be a better way to figure out the offset
  //                  automatically such as using float
  offset: number;
  openUploadNewBundleForm: () => any;
}

class BundlesApp extends React.Component<BundlesAppProps> {
  render() {
    return (
      <>
        <BundleList />

        <UploadBundleForm />
        <UpdateResourceForm />

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: this.props.offset,
            right: 24,
          }}
          onClick={this.props.openUploadNewBundleForm}
        >
          <ContentAdd />
        </FloatingActionButton>
      </>
    );
  }
}

const mapDispatchToProps = {
  openUploadNewBundleForm: () => (
    formDialog.actions.openForm(UPLOAD_BUNDLE_FORM)
  ),
};

export default connect(null, mapDispatchToProps)(BundlesApp);
