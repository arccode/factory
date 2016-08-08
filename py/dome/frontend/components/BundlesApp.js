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
import UploadingTask from './UploadingTask';

var BundlesApp = React.createClass({
  propTypes: {
    openUploadingNewBundleForm: React.PropTypes.func.isRequired,
    dismissUploadingTask: React.PropTypes.func.isRequired,
    uploadingTasks: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  render: function() {
    const {
      openUploadingNewBundleForm,
      dismissUploadingTask,
      uploadingTasks
    } = this.props;

    return (
      <div>
        <BundleList />

        <UploadingBundleForm />
        <UpdatingResourceForm />

        {uploadingTasks.keySeq().toArray().map((taskID, index) => {
          var task = uploadingTasks.get(taskID);
          return (
            <UploadingTask
              key={taskID}
              // state={task.state}
              state={task.get('state')}
              // description={task.description}
              description={task.get('description')}
              style={{
                position: 'fixed',
                padding: 5,
                right: 24,
                bottom: 50 * index + 24  // stack them
              }}
              cancel={() => console.log('not implemented')}
              dismiss={() => dismissUploadingTask(taskID)}
              retry={() => alert('not implemented yet')}
            />
          );
        })}

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: 50 * uploadingTasks.size + 24, // above all uploading tasks
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

function mapStateToProps(state) {
  return {
    uploadingTasks: state.getIn(['bundles', 'uploadingTasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    openUploadingNewBundleForm:
        () => dispatch(Actions.openForm(FormNames.UPLOADING_BUNDLE_FORM)),
    dismissUploadingTask:
        taskID => dispatch(Actions.dismissUploadingTask(taskID))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(BundlesApp);
