// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {arrayMove} from 'react-sortable-hoc';
import {createAction} from 'typesafe-actions';

import error from '@app/error';
import formDialog from '@app/form_dialog';
import project from '@app/project';
import task from '@app/task';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {UPDATE_RESOURCE_FORM, UPLOAD_BUNDLE_FORM} from './constants';
import {getBundles} from './selectors';
import {
  Bundle,
  DeletedResources,
  UpdateResourceRequestPayload,
  UploadBundleRequestPayload,
} from './types';

const receiveBundles = createAction('RECEIVE_BUNDLES', (resolve) =>
  (bundles: Bundle[]) => resolve({bundles}));

const reorderBundlesImpl = createAction('REORDER_BUNDLES', (resolve) =>
  (bundles: Bundle[]) => resolve({bundles}));

const updateBundle = createAction('UPDATE_BUNDLE', (resolve) =>
  (name: string, bundle: Bundle) => resolve({name, bundle}));

const deleteBundleImpl = createAction('DELETE_BUNDLE', (resolve) =>
  (name: string) => resolve({name}));

const addBundle = createAction('ADD_BUNDLE', (resolve) =>
  (bundle: Bundle) => resolve({bundle}));

const receiveDeletedResources = createAction('RECEIVE_GC', (resolve) =>
  (resources: DeletedResources) => resolve({resources}));

export const closeGarbageCollectionSnackbar = createAction('CLOSE_GC');

export const expandBundle = createAction('EXPAND_BUNDLE', (resolve) =>
  (name: string) => resolve({name}));

export const collapseBundle = createAction('COLLAPSE_BUNDLE', (resolve) =>
  (name: string) => resolve({name}));

export const basicActions = {
  receiveBundles,
  reorderBundlesImpl,
  updateBundle,
  deleteBundleImpl,
  addBundle,
  expandBundle,
  collapseBundle,
  receiveDeletedResources,
  closeGarbageCollectionSnackbar,
};

const baseURL = (getState: () => RootState): string => {
  return `/projects/${project.selectors.getCurrentProject(getState())}`;
};

const findBundle = (name: string, getState: () => RootState) =>
  getBundles(getState()).find((b) => b.name === name);

export const fetchBundles = () =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    // TODO(littlecvr): this is also a task but a hidden one, consider unify the
    //                  task handling process. (If adding hidden task we can
    //                  also get rid of _taskOnFinishes in task/actions since
    //                  we only have to add a hidden task after the main task
    //                  as the onFinish callback.)
    try {
      const response = await authorizedAxios().get<Bundle[]>(
        `${baseURL(getState)}/bundles.json`);
      dispatch(receiveBundles(response.data));
    } catch (err) {
      dispatch(error.actions.setAndShowErrorDialog(
        `error fetching bundle list\n\n${err.message}`));
    }
  };

export const reorderBundles = (oldIndex: number, newIndex: number) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const newBundleList =
      arrayMove(getBundles(getState()), oldIndex, newIndex);

    const optimisticUpdate = () => {
      dispatch(reorderBundlesImpl(newBundleList));
    };

    // send the request
    const newBundleNameList = newBundleList.map((b) => b.name);
    await dispatch(task.actions.runTask(
      'Reorder bundles', 'PUT', `${baseURL(getState)}/bundles/`,
      newBundleNameList, optimisticUpdate));
  };

export const activateBundle = (name: string, active: boolean) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const bundle = findBundle(name, getState);
    if (!bundle) {
      return;
    }
    const optimisticUpdate = () => {
      dispatch(updateBundle(name, {...bundle, active}));
    };

    // send the request
    const body = {
      project: project.selectors.getCurrentProject(getState()),
      name,
      active,
    };
    const verb = active ? 'Activate' : 'Deactivate';
    const description = `${verb} bundle "${name}"`;
    await dispatch(task.actions.runTask(
      description, 'PUT', `${baseURL(getState)}/bundles/${name}/`, body,
      optimisticUpdate));
    // TODO(pihsun): Need this hack to refresh bundle list, and disable other
    // active bundle when activating a bundle. Should refine this to
    // optimisticUpdate on frontend.
    await dispatch(fetchBundles());
  };

export const deleteBundle = (name: string) =>
  (dispatch: Dispatch, getState: () => RootState) => (
    dispatch(task.actions.runTask(
      `Delete bundle "${name}"`,
      'DELETE',
      `${baseURL(getState)}/bundles/${name}/`,
      {},
      () => {
        // optimistic update
        dispatch(deleteBundleImpl(name));
      }))
  );

export const startUploadBundle = (data: UploadBundleRequestPayload) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(formDialog.actions.closeForm(UPLOAD_BUNDLE_FORM));

    const optimisticUpdate = () => {
      // TODO(littlecvr): to improve user experience, we should have a variable
      //                  indicating that the bundle is currently being
      //                  uploaded, so we can for example append "(uploading)"
      //                  to bundle name to make it more clear.
      dispatch(addBundle({ // give it an empty bundle
        name: data.name,
        note: data.note,
        active: true,
        resources: {},
      }));
    };

    // send the request
    const description = `Upload bundle "${data.name}"`;
    const bundle = await dispatch(task.actions.runTask<Bundle>(
      description, 'POST', `${baseURL(getState)}/bundles/`, data,
      optimisticUpdate));
    // need to fill in the real data after the request has finished
    dispatch(updateBundle(bundle.name, bundle));
  };

export const startUpdateResource =
  (resourceKey: string, data: UpdateResourceRequestPayload) =>
    async (dispatch: Dispatch, getState: () => RootState) => {
      dispatch(formDialog.actions.closeForm(UPDATE_RESOURCE_FORM));

      const srcBundleName = data.name;
      const dstBundleName = data.newName;

      const oldBundle = findBundle(srcBundleName, getState);
      if (!oldBundle) {
        return;
      }
      const bundle = produce(oldBundle, (draft) => {
        draft.name = dstBundleName;
        draft.note = data.note;
        // reset hash and version of the resource currently being update
        draft.resources[resourceKey].hash = '(waiting for update)';
        draft.resources[resourceKey].version = '(waiting for update)';
      });

      const optimisticUpdate = () => {
        dispatch(addBundle(bundle));

        // for better user experience:
        // - collapse and deactivate the old bundle
        // - expand and activate the new bundle
        // (but we cannot activate the new bundle here because the bundle is not
        //  ready yet, we have to activate it after the task finished)
        dispatch(collapseBundle(srcBundleName));
        dispatch(expandBundle(dstBundleName));
        // we can't deactivate the old bundle now or it will fail if there is
        // only one bundle before this update operation.
      };

      // send the request
      const description =
        `Update bundle "${srcBundleName}" to bundle "${dstBundleName}"`;
      const responseBundle = await dispatch(task.actions.runTask<Bundle>(
        description, 'PUT', `${baseURL(getState)}/bundles/${srcBundleName}/`,
        data, optimisticUpdate));
      dispatch(updateBundle(dstBundleName, responseBundle));
      // activate the new bundle by default for convenience
      dispatch(activateBundle(dstBundleName, true));
      dispatch(activateBundle(srcBundleName, false));
    };

export const startResourcesGarbageCollection = () =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const description = 'Delete unused resources.';

    const deletedFiles = await dispatch(task.actions.runTask<DeletedResources>(
      description, 'POST', `${baseURL(getState)}/resources/gc`, {}));
    dispatch(receiveDeletedResources(deletedFiles));
  };

export const setBundleAsNetboot = (name: string, projectName: string) => (
  project.actions.updateProject(
    projectName,
    {netbootBundle: name},
    `Set netboot bundle to ${name} for project "${projectName}"`)
);

export const downloadResource = (projectName: string,
                                 bundleName: string,
                                 resourceType: string) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    await authorizedAxios().get(
        `projects/${projectName}/bundles/${bundleName}/${resourceType}`, {
      responseType: 'blob',
    }).then((response) => {
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(response.data);
      link.download = resourceType;
      link.click();
      window.URL.revokeObjectURL(link.href);
    }, (axiosError) => {
      const reader = new FileReader();
      reader.onload = () => {
        const message = JSON.parse(reader.result as string);
        dispatch(error.actions.setAndShowErrorDialog(
            `error downloading resource\n\n${message.detail}`));
      };
      reader.readAsText(axiosError.response.data);
    });
  };
