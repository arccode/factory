// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import ContentAdd from 'material-ui/svg-icons/content/add';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import Immutable from 'immutable';
import React from 'react';

import BundleList from './BundleList';
import BundlesActions from '../actions/bundlesactions';
import FormNames from '../constants/FormNames';
import UpdatingResourceForm from './UpdatingResourceForm';
import UploadingBundleForm from './UploadingBundleForm';
import Task from './Task';

var BundlesApp = React.createClass({
  propTypes: {
    openUploadingNewBundleForm: React.PropTypes.func.isRequired,
    dismissTask: React.PropTypes.func.isRequired,
    tasks: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  render: function() {
    const {
      openUploadingNewBundleForm,
      dismissTask,
      tasks
    } = this.props;

    return (
      <div>
        <BundleList />

        <UploadingBundleForm />
        <UpdatingResourceForm />

        {tasks.keySeq().toArray().map((taskID, index) => {
          var task = tasks.get(taskID);
          return (
            <Task
              key={taskID}
              state={task.get('state')}
              description={task.get('description')}
              style={{
                position: 'fixed',
                padding: 5,
                right: 24,
                bottom: 50 * index + 24  // stack them
              }}
              cancel={() => console.log('not implemented')}
              dismiss={() => dismissTask(taskID)}
              retry={() => alert('not implemented yet')}
            />
          );
        })}

        {/* upload button */}
        <FloatingActionButton
          style={{
            position: 'fixed',
            bottom: 50 * tasks.size + 24, // above all uploading tasks
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
    tasks: state.getIn(['bundles', 'tasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    openUploadingNewBundleForm: () =>
        dispatch(BundlesActions.openForm(FormNames.UPLOADING_BUNDLE_FORM)),
    dismissTask:
        taskID => dispatch(BundlesActions.dismissTask(taskID))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(BundlesApp);
