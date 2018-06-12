// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {SortableContainer, SortableElement} from 'react-sortable-hoc';

import * as actions from '../actions';
import Bundle from './Bundle';

// The hierarchy of this component is complicated because of the design of
// react-sortable-hoc. Explaination below:
//
//   BundleList
//   - SortableBundleList (SortableContainer)
//     - SortableBundle (SortableElement)
//       - Bundle
//     - SortableBundle (SortableElement)
//       - Bundle
//
//  SortableBundle is a wrapper of Bundle, but SortableBundleList is not a
//  wrapper of BundleList -- BundleList is the wrapper of SortableBundleList.

const SortableBundle = SortableElement(
    ({bundle}) => <Bundle bundle={bundle} />);

const SortableBundleList = SortableContainer(({bundles}) => (
  <div>
    {bundles.map((bundle, index) => (
      <SortableBundle key={bundle.get('name')} index={index} bundle={bundle} />
    ))}
  </div>
));

class BundleList extends React.Component {
  static propTypes = {
    bundles: PropTypes.instanceOf(Immutable.List).isRequired,
    handleRefresh: PropTypes.func.isRequired,
    handleReorder: PropTypes.func.isRequired,
  };

  componentDidMount() {
    this.props.handleRefresh();
  }

  render() {
    return (
      <SortableBundleList
        lockAxis='y'
        useDragHandle={true}
        useWindowAsScrollContainer={true}
        onSortEnd={this.props.handleReorder}
        bundles={this.props.bundles}
      />
    );
  }
}

function mapStateToProps(state) {
  return {
    bundles: state.getIn(['bundle', 'entries']),
  };
}

function mapDispatchToProps(dispatch) {
  return {
    handleRefresh: () => dispatch(actions.fetchBundles()),
    handleReorder: ({oldIndex, newIndex}) => (
      dispatch(actions.reorderBundles(oldIndex, newIndex))
    ),
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(BundleList);
