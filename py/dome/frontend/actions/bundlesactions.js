// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import DomeActions from './domeactions';
import FormNames from '../constants/FormNames';

function baseURL(getState) {
  return `/projects/${getState().getIn(['dome', 'currentProject'])}`;
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
  DomeActions.authorizedFetch(`${baseURL(getState)}/bundles.json`, {})
  .then(response => {
    // a response can only be read once, workaround to read the response twice
    // if needed
    let responseCopy = response.clone();

    response.json().then(json => {
      dispatch(receiveBundles(json));
    }, error => {
      responseCopy.text().then(text => {
        dispatch(DomeActions.setAndShowErrorDialog(
            'error parsing bundle list response\n\n' +
            `${error.message}\n\n` +
            text
        ));
      });
    });
  }, error => {
    dispatch(DomeActions.setAndShowErrorDialog(
        `error fetching bundle list\n\n${error.message}`
    ));
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
      newBundleNameList, {onCancel}
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
  var body = {
    project: getState().getIn(['dome', 'currentProject']),
    name,
    active
  };
  var verb = active ? 'Activate' : 'Deactivate';
  var description = `${verb} bundle "${name}"`;
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}`, body,
      {onCancel}
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
  var body = {
    // TODO(littlecvr): refine the back-end API so we don't need project here,
    //                  the URL already contains project
    project: getState().getIn(['dome', 'currentProject']),
    name,
    rules,
  };
  var description = `Change rules of bundle "${name}"`;
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}`, body,
      {onCancel}
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
      {}, {onCancel}
  ));
};

const startUploadingBundle = data => (dispatch, getState) => {
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
      name: data.name,
      note: data.note,
      active: true,
      resources: {},
      rules: {}
    }
  });

  // need to fill in the real data after the request has finished
  var onFinish = response => response.json().then(json => dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name: data.name,
    bundle: json
  }));

  // send the request
  var description = `Upload bundle "${data.name}"`;
  dispatch(DomeActions.createTask(
      description, 'POST', `${baseURL(getState)}/bundles`, data,
      {onFinish, onCancel}
  ));
};

const startUpdatingResource = (resourceKey, data) => (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM));

  var onCancel = buildOnCancel(dispatch, getState);
  var srcBundleName = data.name;
  var dstBundleName = data.newName;

  // optimistic update
  var bundle = findBundle(srcBundleName, getState);
  bundle['name'] = dstBundleName;
  bundle['note'] = data.note;
  // reset hash and version of the resource currently being update
  bundle['resources'][resourceKey]['hash'] = '(waiting for update)';
  bundle['resources'][resourceKey]['version'] = '(waiting for update)';
  dispatch({
    type: ActionTypes.ADD_BUNDLE,
    bundle
  });

  // for better user experience:
  // - collapse and deactivate the old bundle
  // - expand and activate the new bundle
  // (but we cannot activate the new bundle here because the bundle is not ready
  //  yet, we have to activate it after the task finished)
  dispatch(collapseBundle(srcBundleName));
  dispatch(expandBundle(dstBundleName));
  dispatch(activateBundle(srcBundleName, false));

  // need to fill in the real data after the request has finished
  var onFinish = response => response.json().then(
    json => dispatch({
      type: ActionTypes.UPDATE_BUNDLE,
      name: dstBundleName,
      bundle: json
    })
  ).then(
    // activate the new bundle by default for convenience
    () => dispatch(
      activateBundle(dstBundleName, true)
    )
  );

  // send the request
  var description =
      `Update bundle "${srcBundleName}" to bundle "${dstBundleName}"`;
  dispatch(DomeActions.createTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${srcBundleName}`, data,
      {onFinish, onCancel}
  ));
};

const expandBundle = name => ({
  type: ActionTypes.EXPAND_BUNDLE,
  name
});

const collapseBundle = name => ({
  type: ActionTypes.COLLAPSE_BUNDLE,
  name
});

export default {
  fetchBundles, reorderBundles, activateBundle, changeBundleRules, deleteBundle,
  startUploadingBundle, startUpdatingResource,
  expandBundle, collapseBundle
};
