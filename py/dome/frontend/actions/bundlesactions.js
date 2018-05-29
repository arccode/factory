// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import FormNames from '../constants/FormNames';

import DomeActions from './domeactions';
import TaskActions from './taskactions';

function baseURL(getState) {
  return `/projects/${getState().getIn(['dome', 'currentProject'])}`;
}

// TODO(pihsun): Have a better way to handle task cancellation.
function buildOnCancel(dispatch, getState) {
  const bundleListSnapshot = getState().getIn(['bundles', 'entries']);
  return () => dispatch(receiveBundles(bundleListSnapshot.toJS()));
}

function findBundle(name, getState) {
  return getState().getIn(['bundles', 'entries']).find(
      (b) => b.get('name') == name
  ).toJS();
}

const receiveBundles = (bundles) => ({
  type: ActionTypes.RECEIVE_BUNDLES,
  bundles,
});

const fetchBundles = () => async (dispatch, getState) => {
  // TODO(littlecvr): this is also a task but a hidden one, consider unify the
  //                  task handling process. (If adding hidden task we can also
  //                  get rid of _taskOnFinishes in DomeActions since we only
  //                  have to add a hidden task after the main task as the
  //                  onFinish callback.)
  try {
    const response = await DomeActions.authorizedFetch(
        `${baseURL(getState)}/bundles.json`, {});
    // a response can only be read once, workaround to read the response
    // twice if needed
    const responseCopy = response.clone();
    try {
      const json = await response.json();
      dispatch(receiveBundles(json));
    } catch (error) {
      const text = await responseCopy.text();
      dispatch(DomeActions.setAndShowErrorDialog(
          'error parsing bundle list response\n\n' +
          `${error.message}\n\n` + text));
    }
  } catch (error) {
    dispatch(DomeActions.setAndShowErrorDialog(
        `error fetching bundle list\n\n${error.message}`));
  }
};

const reorderBundles = (oldIndex, newIndex) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);
  const newBundleList = arrayMove(
      getState().getIn(['bundles', 'entries']).toJS(), oldIndex, newIndex);

  // optimistic update
  dispatch({
    type: ActionTypes.REORDER_BUNDLES,
    bundles: newBundleList,
  });

  // send the request
  const newBundleNameList = newBundleList.map((b) => b['name']);
  const {cancel} = await dispatch(TaskActions.runTask(
      'Reorder bundles', 'PUT', `${baseURL(getState)}/bundles/`,
      newBundleNameList));
  if (cancel) {
    onCancel();
  }
};

const activateBundle = (name, active) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  const bundle = findBundle(name, getState);
  bundle['active'] = active;
  dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name,
    bundle,
  });

  // send the request
  const body = {
    project: getState().getIn(['dome', 'currentProject']),
    name,
    active,
  };
  const verb = active ? 'Activate' : 'Deactivate';
  const description = `${verb} bundle "${name}"`;
  const {cancel} = await dispatch(TaskActions.runTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}/`, body));
  if (cancel) {
    onCancel();
  }
};

const changeBundleRules = (name, rules) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  const bundle = findBundle(name, getState);
  bundle['rules'] = rules;
  dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name,
    bundle,
  });

  // send the request
  const body = {
    // TODO(littlecvr): refine the back-end API so we don't need project here,
    //                  the URL already contains project
    project: getState().getIn(['dome', 'currentProject']),
    name,
    rules,
  };
  const description = `Change rules of bundle "${name}"`;
  const {cancel} = await dispatch(TaskActions.runTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}/`, body));
  if (cancel) {
    onCancel();
  }
};

const deleteBundle = (name) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.DELETE_BUNDLE,
    name,
  });

  // send the request
  const description = `Delete bundle "${name}"`;
  const {cancel} = await dispatch(TaskActions.runTask(
      description, 'DELETE', `${baseURL(getState)}/bundles/${name}/`, {}));
  if (cancel) {
    onCancel();
  }
};

const startUploadingBundle = (data) => async (dispatch, getState) => {
  dispatch(DomeActions.closeForm(FormNames.UPLOADING_BUNDLE_FORM));

  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: ActionTypes.ADD_BUNDLE,
    // TODO(littlecvr): to improve user experience, we should have a variable
    //                  indicating that the bundle is currently being uploaded,
    //                  so we can for example append "(uploading)" to bundle
    //                  name to make it more clear, or we can make the resource
    //                  and rule table totally unexpandable (since there are
    //                  nothing there for now, expanding them is useless)
    bundle: { // give it an empty bundle
      name: data.name,
      note: data.note,
      active: true,
      resources: {},
      rules: {},
    },
  });

  // send the request
  const description = `Upload bundle "${data.name}"`;
  const {cancel, response} = await dispatch(TaskActions.runTask(
      description, 'POST', `${baseURL(getState)}/bundles/`, data));
  if (cancel) {
    onCancel();
    return;
  }
  const bundle = await response.json();
  // need to fill in the real data after the request has finished
  dispatch({
    type: ActionTypes.UPDATE_BUNDLE,
    name: data.name,
    bundle,
  });
};

const startUpdatingResource = (resourceKey, data) => (
  async (dispatch, getState) => {
    dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM));

    const onCancel = buildOnCancel(dispatch, getState);
    const srcBundleName = data.name;
    const dstBundleName = data.newName;

    // optimistic update
    const bundle = findBundle(srcBundleName, getState);
    bundle['name'] = dstBundleName;
    bundle['note'] = data.note;
    // reset hash and version of the resource currently being update
    bundle['resources'][resourceKey]['hash'] = '(waiting for update)';
    bundle['resources'][resourceKey]['version'] = '(waiting for update)';
    dispatch({
      type: ActionTypes.ADD_BUNDLE,
      bundle,
    });

    // for better user experience:
    // - collapse and deactivate the old bundle
    // - expand and activate the new bundle
    // (but we cannot activate the new bundle here because the bundle is not
    //  ready yet, we have to activate it after the task finished)
    dispatch(collapseBundle(srcBundleName));
    dispatch(expandBundle(dstBundleName));
    // we can't deactivate the old bundle now or it will fail if there is only
    // one bundle before this update operation.

    // send the request
    const description =
        `Update bundle "${srcBundleName}" to bundle "${dstBundleName}"`;
    const {cancel, response} = await dispatch(TaskActions.runTask(
        description, 'PUT', `${baseURL(getState)}/bundles/${srcBundleName}/`,
        data));
    if (cancel) {
      onCancel();
      return;
    }
    const json = await response.json();
    dispatch({
      type: ActionTypes.UPDATE_BUNDLE,
      name: dstBundleName,
      bundle: json,
    });
    // activate the new bundle by default for convenience
    dispatch(activateBundle(dstBundleName, true));
    dispatch(activateBundle(srcBundleName, false));
  }
);

const expandBundle = (name) => ({
  type: ActionTypes.EXPAND_BUNDLE,
  name,
});

const collapseBundle = (name) => ({
  type: ActionTypes.COLLAPSE_BUNDLE,
  name,
});

export default {
  fetchBundles, reorderBundles, activateBundle, changeBundleRules, deleteBundle,
  startUploadingBundle, startUpdatingResource,
  expandBundle, collapseBundle,
};
