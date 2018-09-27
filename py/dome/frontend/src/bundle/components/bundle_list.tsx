// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {connect} from 'react-redux';
import {SortableContainer, SortableElement} from 'react-sortable-hoc';

import {RootState} from '@app/types';

import {DispatchProps} from '@common/types';

import {fetchBundles, reorderBundles} from '../actions';
import {getBundles} from '../selectors';
import {Bundle} from '../types';

import BundleComponent, {BundleComponentOwnProps} from './bundle_component';

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

const SortableBundle = SortableElement<BundleComponentOwnProps>(
  ({bundle, bundles}) => <BundleComponent bundle={bundle} bundles={bundles} />);

const SortableBundleList = SortableContainer<{bundles: Bundle[]}>(
  ({bundles}) => (
    <div>
      {bundles.map((bundle, index) => (
        <SortableBundle
          key={bundle.name}
          index={index}
          bundle={bundle}
          bundles={bundles}
        />
      ))}
    </div>
  ));

type BundleListProps =
  ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

class BundleList extends React.Component<BundleListProps> {
  componentDidMount() {
    this.props.fetchBundles();
  }

  handleReorder =
    ({oldIndex, newIndex}: {oldIndex: number, newIndex: number}) => {
      if (oldIndex !== newIndex) {
        this.props.reorderBundles(oldIndex, newIndex);
      }
    }

  render() {
    return (
      <SortableBundleList
        lockAxis="y"
        useDragHandle
        useWindowAsScrollContainer
        onSortEnd={this.handleReorder}
        bundles={this.props.bundles}
      />
    );
  }
}

const mapStateToProps = (state: RootState) => ({bundles: getBundles(state)});

const mapDispatchToProps = {
  fetchBundles,
  reorderBundles,
};

export default connect(mapStateToProps, mapDispatchToProps)(BundleList);
