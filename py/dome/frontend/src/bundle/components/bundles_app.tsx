// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Portal from '@material-ui/core/Portal';
import AddIcon from '@material-ui/icons/Add';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {UPLOAD_BUNDLE_FORM} from '../constants';

import BundleList from './bundle_list';
import UpdateResourceForm from './update_resource_form';
import UploadBundleForm from './upload_bundle_form';

interface BundlesAppProps {
  overlay: Element | null;
  openUploadNewBundleForm: () => any;
}

const BundlesApp: React.SFC<BundlesAppProps> =
  ({overlay, openUploadNewBundleForm}) => (
    <>
      <BundleList />

      <UploadBundleForm />
      <UpdateResourceForm />

      {/* upload button */}
      {overlay &&
        <Portal container={overlay}>
          <Button
            variant="fab"
            color="primary"
            onClick={openUploadNewBundleForm}
          >
            <AddIcon />
          </Button>
        </Portal>
      }
    </>
  );

const mapDispatchToProps = {
  openUploadNewBundleForm: () => (
    formDialog.actions.openForm(UPLOAD_BUNDLE_FORM)
  ),
};

export default connect(null, mapDispatchToProps)(BundlesApp);
