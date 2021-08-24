// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Portal from '@material-ui/core/Portal';
import AddIcon from '@material-ui/icons/Add';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {DispatchProps} from '@common/types';

import {UPLOAD_BUNDLE_FORM} from '../constants';

import BundleList from './bundle_list';
import ResourcesGarbageCollectionButton from './resources_gc';
import UpdateResourceDialog from './update_resource_dialog';
import UploadBundleDialog from './upload_bundle_dialog';

interface BundlesAppOwnProps {
  overlay: Element | null;
}

type BundlesAppProps =
  BundlesAppOwnProps & DispatchProps<typeof mapDispatchToProps>;

const BundlesApp: React.SFC<BundlesAppProps> =
  ({overlay, openUploadNewBundleForm}) => (
    <>
      <BundleList />

      <UploadBundleDialog />
      <UpdateResourceDialog />

      {/* upload button */}
      {overlay &&
        <>
          <Portal container={overlay}>
            <Button
              variant="fab"
              color="primary"
              title="Upload Factory Bundle (zip or {gzip|bzip2|xz} compressed tarball)"
              onClick={openUploadNewBundleForm}
            >
              <AddIcon />
            </Button>
          </Portal>
          <Portal container={overlay}>
            <ResourcesGarbageCollectionButton />
          </Portal>
        </>
      }
    </>
  );

const mapDispatchToProps = {
  openUploadNewBundleForm: () => (
    formDialog.actions.openForm(UPLOAD_BUNDLE_FORM)
  ),
};

export default connect(null, mapDispatchToProps)(BundlesApp);
