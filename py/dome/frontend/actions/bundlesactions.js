// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import DomeActions from './domeactions';
import FormNames from '../constants/FormNames';

function baseURL(getState) {
  return `/boards/${getState().getIn(['dome', 'currentBoard'])}`;
}

function buildOnCancel(dispatch, getState) {
  var bundleListSnapshot = getState().getIn(['bundles', 'entries']).toJS();
  return () => dispatch(receiveBundles(bundleListSnapshot));
}

function findBundle(name, getState) {
  return getState().getIn(['bundles', 'entries']).find(
      b => b.get('name') == name
  ).toJS();
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
  var onCancel = buildOnCancel(dispatch, getState);
  var newBundleList = arrayMove(
      getState().getIn(['bundles', 'entries']).toJS(), oldIndex, newIndex);

  // optimistic update
  dispatch({
    type: ActionTypes.REORDER_BUNDLES,
    bundles: newBundleList
  });

  // send the request
  var newBundleNameList = newBundleList.map(b => b['name']);
  dispatch(DomeActions.createTask(
      'Reorder bundles', 'PUT', `${baseURL(getState)}/bundles`,
      JSON.stringify(newBundleNameList), null, onCancel, 'application/json'
  ));
};

const activateBundle = (name, active) => (dispatch, getState) => {
  var onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  var bundle = findBundle(name, getState);
  bundle['active'] = active;
  dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name,
    bundle
  });

  // send the request
  var formData = new FormData();
  formData.append('board', getState().getIn(['dome', 'currentBoard']));
  formData.append('name', name);
  formData.append('active', active);
  var verb = active ? 'Activate' : 'Deactivate';
  var description = `${verb} bundle "${name}"`;
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}`, formData,
      null, onCancel
  ));
};

const changeBundleRules = (name, rules) => (dispatch, getState) => {
  var onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  var bundle = findBundle(name, getState);
  bundle['rules'] = rules;
  dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name,
    bundle
  });

  // send the request
  var data = {
    // TODO(littlecvr): refine the back-end API so we don't need board here, the
    //                  URL already contains board
    board: getState().getIn(['dome', 'currentBoard']),
    name,
    rules,
  };
  var description = `Change rules of bundle "${name}"`;
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}`,
      JSON.stringify(data), null, onCancel, 'application/json'
  ));
};

const deleteBundle = name => (dispatch, getState) => {
  var onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.DELETE_BUNDLE,
    name
  });

  // send the request
  var description = `Delete bundle "${name}"`;
  dispatch(DomeActions.createTask(
      description, 'DELETE', `${baseURL(getState)}/bundles/${name}`,
      new FormData(), null, onCancel
  ));
};

const startUploadingBundle = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPLOADING_BUNDLE_FORM));

  var onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.ADD_BUNDLE,
    // TODO(littlecvr): to improve user experience, we should have a variable
    //                  indicating that the bundle is currently being uploaded,
    //                  so we can for example append "(uploading)" to bundle
    //                  name to make it more clear, or we can make the resource
    //                  and rule table totally unexpandable (since there are
    //                  nothing there for now, expanding them is useless)
    bundle: {  // give it an empty bundle
      name: formData.get('name'),
      note: formData.get('note'),
      active: true,
      resources: {},
      rules: {}
    }
  });

  // need to fill in the real data after the request has finished
  var onFinish = response => response.json().then(json => dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name: formData.get('name'),
    bundle: json
  }));

  // send the request
  var description = `Upload bundle "${formData.get('name')}"`;
  dispatch(DomeActions.createTask(
      description, 'POST', `${baseURL(getState)}/bundles`, formData, onFinish,
      onCancel
  ));
};

const startUpdatingResource = formData => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM));

  var onCancel = buildOnCancel(dispatch, getState);
  var srcBundleName = formData.get('src_bundle_name');
  var dstBundleName = formData.get('dst_bundle_name');

  // optimistic update
  var bundle = findBundle(srcBundleName, getState);
  bundle['note'] = formData.get('note');
  // reset hash and version of the resource currently being update
  var resourceType = formData.get('resource_type');
  bundle['resources'][resourceType]['hash'] = '(waiting for update)';
  bundle['resources'][resourceType]['version'] = '(waiting for update)';
  if (dstBundleName != '') {
    // duplicate the src bundle if it's not an in-place update
    bundle['name'] = dstBundleName;
    dispatch({
      type: ActionTypes.ADD_BUNDLE,
      bundle
    });
  } else {
    dispatch({
      type: ActionTypes.UPDATE_BUNDLE,
      name: srcBundleName,
      bundle
    });
  }

  // need to fill in the real data after the request has finished
  var onFinish = response => response.json().then(json => dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name: dstBundleName == '' ? srcBundleName : dstBundleName,
    bundle: json
  }));

  // send the request
  var description = `Update bundle "${srcBundleName}"`;
  if (dstBundleName != '') {
    description += ` to bundle "${dstBundleName}"`;
  }
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/resources`, formData, onFinish,
      onCancel
  ));
};

export default {
  fetchBundles, reorderBundles, activateBundle, changeBundleRules, deleteBundle,
  startUploadingBundle, startUpdatingResource
};
