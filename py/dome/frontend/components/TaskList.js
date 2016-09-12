// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card} from 'material-ui/Card';
import {connect} from 'react-redux';
import Immutable from 'immutable';
import React from 'react';

import DomeActions from '../actions/domeactions';
import Task from './Task';

var TaskList = React.createClass({
  propTypes: {
    tasks: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    dismissTask: React.PropTypes.func.isRequired,
    retryTask: React.PropTypes.func.isRequired
  },

  render() {
    return (
      <Card
        style={{position: 'fixed', right: 24, bottom: 24}}
        containerStyle={{display: 'table'}}
      >
        {this.props.tasks.keySeq().sort().toArray().map(taskID => {
          var task = this.props.tasks.get(taskID);
          return (
            <Task
              key={taskID}
              state={task.get('state')}
              description={task.get('description')}
              cancel={() => this.props.cancelTask(taskID)}
              dismiss={() => this.props.dismissTask(taskID)}
              retry={() => this.props.retryTask(taskID)}
            />
          );
        })}
      </Card>
    );
  }
});

function mapStateToProps(state) {
  return {
    tasks: state.getIn(['dome', 'tasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    cancelTask: taskID => console.warn('not implemented yet'),
    dismissTask: taskID => dispatch(DomeActions.dismissTask(taskID)),
    retryTask: taskID => console.warn('not implemented yet')
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(TaskList);
