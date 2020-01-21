# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

GCLOUD_PROJECT = '${GCLOUD_PROJECT}'
BUNDLE_BUCKET = '${BUNDLE_BUCKET}'
PUBSUB_SUBSCRIPTION = '${PUBSUB_SUBSCRIPTION}'
RESPONSE_QUEUE = ('projects/${GCLOUD_PROJECT}'
                  '/locations/us-central1/queues/bundle-tasks-result')
