// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {arrayMove} from 'react-sortable-hoc';

import error from '@app/error';
import formDialog from '@app/formDialog';
import project from '@app/project';
import task from '@app/task';
import {authorizedAxios} from '@common/utils';

import actionTypes from './actionTypes';
import {UPDATING_RESOURCE_FORM, UPLOADING_BUNDLE_FORM} from './constants';
import {getBundles} from './selectors';

const baseURL = (getState) => {
  return `/projects/${project.selectors.getCurrentProject(getState())}`;
};

// TODO(pihsun): Have a better way to handle task cancellation.
const buildOnCancel = (dispatch, getState) => {
  const bundleListSnapshot = getBundles(getState());
  return () => dispatch(receiveBundles(bundleListSnapshot.toJS()));
};

const findBundle = (name, getState) => {
  return getBundles(getState()).find((b) => b.get('name') === name).toJS();
};

export const receiveBundles = (bundles) => ({
  type: actionTypes.RECEIVE_BUNDLES,
  bundles,
});

export const fetchBundles = () => async (dispatch, getState) => {
  // TODO(littlecvr): this is also a task but a hidden one, consider unify the
  //                  task handling process. (If adding hidden task we can also
  //                  get rid of _taskOnFinishes in task/actions since we only
  //                  have to add a hidden task after the main task as the
  //                  onFinish callback.)
  try {
    const response = await authorizedAxios().get(
        `${baseURL(getState)}/bundles.json`);
    dispatch(receiveBundles(response.data));
  } catch (err) {
    dispatch(error.actions.setAndShowErrorDialog(
        `error fetching bundle list\n\n${error.message}`));
  }
};

export const reorderBundles = (oldIndex, newIndex) =>
  async (dispatch, getState) => {
    const onCancel = buildOnCancel(dispatch, getState);
    const newBundleList =
        arrayMove(getBundles(getState()).toJS(), oldIndex, newIndex);

    // optimistic update
    dispatch({
      type: actionTypes.REORDER_BUNDLES,
      bundles: newBundleList,
    });

    // send the request
    const newBundleNameList = newBundleList.map((b) => b.name);
    const {cancel} = await dispatch(task.actions.runTask(
        'Reorder bundles', 'PUT', `${baseURL(getState)}/bundles/`,
        newBundleNameList));
    if (cancel) {
      onCancel();
    }
  };

export const activateBundle = (name, active) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  const bundle = findBundle(name, getState);
  bundle.active = active;
  dispatch({
    type: actionTypes.UPDATE_BUNDLE,
    name,
    bundle,
  });

  // send the request
  const body = {
    project: project.selectors.getCurrentProject(getState()),
    name,
    active,
  };
  const verb = active ? 'Activate' : 'Deactivate';
  const description = `${verb} bundle "${name}"`;
  const {cancel} = await dispatch(task.actions.runTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}/`, body));
  if (cancel) {
    onCancel();
  }
};

export const changeBundleRules = (name, rules) =>
  async (dispatch, getState) => {
    const onCancel = buildOnCancel(dispatch, getState);

    // optimistic update
    const bundle = findBundle(name, getState);
    bundle.rules = rules;
    dispatch({
      type: actionTypes.UPDATE_BUNDLE,
      name,
      bundle,
    });

    // send the request
    const body = {
      // TODO(littlecvr): refine the back-end API so we don't need project here,
      //                  the URL already contains project
      project: project.selectors.getCurrentProject(getState()),
      name,
      rules,
    };
    const description = `Change rules of bundle "${name}"`;
    const {cancel} = await dispatch(task.actions.runTask(
        description, 'PUT', `${baseURL(getState)}/bundles/${name}/`, body));
    if (cancel) {
      onCancel();
    }
  };

export const deleteBundle = (name) => async (dispatch, getState) => {
  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: actionTypes.DELETE_BUNDLE,
    name,
  });

  // send the request
  const description = `Delete bundle "${name}"`;
  const {cancel} = await dispatch(task.actions.runTask(
      description, 'DELETE', `${baseURL(getState)}/bundles/${name}/`, {}));
  if (cancel) {
    onCancel();
  }
};

export const startUploadingBundle = (data) => async (dispatch, getState) => {
  dispatch(formDialog.actions.closeForm(UPLOADING_BUNDLE_FORM));

  const onCancel = buildOnCancel(dispatch, getState);

  // optimistic update
  dispatch({
    type: actionTypes.ADD_BUNDLE,
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
  const {cancel, response} = await dispatch(task.actions.runTask(
      description, 'POST', `${baseURL(getState)}/bundles/`, data));
  if (cancel) {
    onCancel();
    return;
  }
  const bundle = response.data;
  // need to fill in the real data after the request has finished
  dispatch({
    type: actionTypes.UPDATE_BUNDLE,
    name: data.name,
    bundle,
  });
};

export const startUpdatingResource = (resourceKey, data) => (
  async (dispatch, getState) => {
    dispatch(formDialog.actions.closeForm(UPDATING_RESOURCE_FORM));

    const onCancel = buildOnCancel(dispatch, getState);
    const srcBundleName = data.name;
    const dstBundleName = data.newName;

    // optimistic update
    const bundle = findBundle(srcBundleName, getState);
    bundle.name = dstBundleName;
    bundle.note = data.note;
    // reset hash and version of the resource currently being update
    bundle.resources[resourceKey].hash = '(waiting for update)';
    bundle.resources[resourceKey].version = '(waiting for update)';
    dispatch({
      type: actionTypes.ADD_BUNDLE,
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
    const {cancel, response} = await dispatch(task.actions.runTask(
        description, 'PUT', `${baseURL(getState)}/bundles/${srcBundleName}/`,
        data));
    if (cancel) {
      onCancel();
      return;
    }
    dispatch({
      type: actionTypes.UPDATE_BUNDLE,
      name: dstBundleName,
      bundle: response.data,
    });
    // activate the new bundle by default for convenience
    dispatch(activateBundle(dstBundleName, true));
    dispatch(activateBundle(srcBundleName, false));
  }
);

export const expandBundle = (name) => ({
  type: actionTypes.EXPAND_BUNDLE,
  name,
});

export const collapseBundle = (name) => ({
  type: actionTypes.COLLAPSE_BUNDLE,
  name,
});

export const setBundleAsNetboot = (name, projectName) => (
  project.actions.updateProject(
      projectName, {netbootBundle: name, umpireEnabled: true})
);
