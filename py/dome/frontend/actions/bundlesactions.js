// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';
import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import DomeActions from './domeactions';
import FormNames from '../constants/FormNames';

function baseURL(getState) {
  return `/boards/${getState().getIn(['dome', 'currentBoard'])}`;
}

const receiveBundles = bundles => ({
  type: ActionTypes.RECEIVE_BUNDLES,
  bundles
});

const fetchBundles = () => (dispatch, getState) => {
  // TODO(littlecvr): this is also a task but a hidden one, consider unify the
  //                  task handling process. (If adding hidden task we can also
  //                  get rid of _taskOnFinishes in DomeActions since we only
  //                  have to add a hidden task after the main task as the
  //                  onFinish callback.)
  fetch(`${baseURL(getState)}/bundles.json`).then(response => {
    response.json().then(json => {
      dispatch(receiveBundles(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.error('error parsing bundle list response');
      console.error(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.error('error fetching bundle list');
    console.error(error);
  });
};

const reorderBundles = (oldIndex, newIndex) => (dispatch, getState) => {
  var new_bundle_list = getState().getIn(['bundles', 'entries']).map(bundle => (
      bundle.get('name')
  )).toArray();
  new_bundle_list = arrayMove(new_bundle_list, oldIndex, newIndex);
  var taskDescription = 'Reorder bundles';

  dispatch(DomeActions.createTask(
      taskDescription, 'PUT', `${baseURL(getState)}/bundles`,
      JSON.stringify(new_bundle_list), () => dispatch(fetchBundles()),
      'application/json'
  ));
};

const activateBundle = (name, active) => (dispatch, getState) => {
  var formData = new FormData();
  formData.append('board', getState().getIn(['dome', 'currentBoard']));
  formData.append('name', name);
  formData.append('active', active);
  var verb = active ? 'Activate' : 'Deactivate';
  var taskDescription = `${verb} bundle "${name}"`;

  dispatch(DomeActions.createTask(
      taskDescription, 'PUT', `${baseURL(getState)}/bundles/${name}`, formData,
      () => dispatch(fetchBundles())
  ));
};

const changeBundleRules = (name, rules) => (dispatch, getState) => {
  var data = {
    board: getState().getIn(['dome', 'currentBoard']),
    name,
    rules,
  };
  var taskDescription = `Change rules of bundle "${name}"`;

  dispatch(DomeActions.createTask(
      taskDescription, 'PUT', `${baseURL(getState)}/bundles/${name}`,
      JSON.stringify(data), () => dispatch(fetchBundles()), 'application/json'
  ));
};

const deleteBundle = name => (dispatch, getState) => {
  var taskDescription = `Delete bundle "${name}"`;
  dispatch(DomeActions.createTask(
      taskDescription, 'DELETE', `${baseURL(getState)}/bundles/${name}`,
      new FormData(), () => dispatch(fetchBundles())
  ));
};

const startUploadingBundle = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPLOADING_BUNDLE_FORM));
  var bundleName = formData.get('name');
  var taskDescription = `Upload bundle "${bundleName}"`;
  dispatch(DomeActions.createTask(
      taskDescription, 'POST', `${baseURL(getState)}/bundles`, formData,
      () => dispatch(fetchBundles())
  ));
};

const startUpdatingResource = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM));
  var srcBundleName = formData.get('src_bundle_name');
  var taskDescription = `Update bundle "${srcBundleName}"`;
  var dstBundleName = formData.get('dst_bundle_name');
  if (dstBundleName != '') {
    taskDescription += ` to bundle "${dstBundleName}"`;
  }
  dispatch(DomeActions.createTask(
      taskDescription, 'PUT', `${baseURL(getState)}/resources`, formData,
      () => dispatch(fetchBundles())
  ));
};

export default {
  fetchBundles, reorderBundles, activateBundle, changeBundleRules, deleteBundle,
  startUploadingBundle, startUpdatingResource
};
