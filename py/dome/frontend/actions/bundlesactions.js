// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';
import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import DomeActions from './domeactions';
import FormNames from '../constants/FormNames';

const receiveBundles = bundles => ({
  type: ActionTypes.RECEIVE_BUNDLES,
  bundles
});

const fetchBundles = () => (dispatch, getState) => {
  fetch(`${DomeActions.apiURL(getState)}/bundles.json`).then(response => {
    response.json().then(json => {
      dispatch(receiveBundles(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.log('error parsing bundle list response');
      console.log(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.log('error fetching bundle list');
    console.log(error);
  });
};

const reorderBundles = (oldIndex, newIndex) => (dispatch, getState) => {
  var new_bundle_list = getState().getIn(['bundles', 'entries']).map(bundle => (
      bundle.get('name')
  )).toArray();
  new_bundle_list = arrayMove(new_bundle_list, oldIndex, newIndex);
  var taskDescription = 'Reordering bundles...';

  DomeActions.createAndStartTask(dispatch, getState, taskDescription, 'PUT',
                                 'bundles', JSON.stringify(new_bundle_list),
                                 'application/json')
      .then(() => dispatch(fetchBundles()));
};

const activateBundle = (name, active) => (dispatch, getState) => {
  var formData = new FormData();
  formData.append('board', getState().getIn(['dome', 'currentBoard']));
  formData.append('name', name);
  formData.append('active', active);
  var verb = active ? 'Activating' : 'Deactivating';
  var taskDescription = `${verb} bundle ${name}...`;
  // TODO(littlecvr): this function can do more than it looks like, rename it
  DomeActions.createAndStartTask(dispatch, getState, taskDescription, 'PUT',
                                 `bundles/${name}`, formData)
      .then(() => dispatch(fetchBundles()));
};

const deleteBundle = name => (dispatch, getState) => {
  var formData = new FormData();
  var taskDescription = `Deleting bundle ${name}...`;
  // TODO(littlecvr): this function can do more than it looks like, rename it
  DomeActions.createAndStartTask(dispatch, getState, taskDescription, 'DELETE',
                                 `bundles/${name}`, new FormData())
      .then(() => dispatch(fetchBundles()));
};

const startUploadingBundle = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPLOADING_BUNDLE_FORM));
  var bundleName = formData.get('name');
  var taskDescription = `Uploading bundle ${bundleName}...`;
  DomeActions.createAndStartTask(dispatch, getState, taskDescription, 'POST',
                                 'bundles', formData)
      .then(() => dispatch(fetchBundles()));
};

const startUpdatingResource = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM));
  var bundleName = formData.get('src_bundle_name');
  var taskDescription = `Updating bundle ${bundleName}...`;
  DomeActions.createAndStartTask(dispatch, getState, taskDescription, 'PUT',
                                 'resources', formData)
      .then(() => dispatch(fetchBundles()));
};

export default {
  fetchBundles, reorderBundles, activateBundle, deleteBundle,
  startUploadingBundle, startUpdatingResource
};
