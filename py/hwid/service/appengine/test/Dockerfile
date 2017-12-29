# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM python:2.7

RUN cd /usr/src && \
  wget https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-182.0.0-linux-x86_64.tar.gz && \
  tar xvf google-cloud-sdk-182.0.0-linux-x86_64.tar.gz && \
  google-cloud-sdk/install.sh \
      --rc-path /root/.bashrc \
      --additional-components app-engine-python app-engine-python-extras \
      --quiet && \
  rm google-cloud-sdk-182.0.0-linux-x86_64.tar.gz && \
  pip install \
      mox==0.5.3 \
      mock==2.0.0 \
      protorpc-standalone==0.9.1 \
      PyYaml==3.11 \
      GoogleAppEngineCloudStorageClient==1.9.22.1 \
      google-endpoints==2.4.5 \
      protorpc-standalone==0.9.1 \
      webapp2==3.0.0b1 \
      WebTest==2.0.29

ARG workdir="/usr/src/"

ADD factory/py "${workdir}/cros/factory/py"
ADD factory/py_pkg "${workdir}/cros/factory/py_pkg"
ADD chromeos-hwid/py "${workdir}/cros/chromeos-hwid/py"

ENV PYTHONPATH=/usr/src/google-cloud-sdk/platform/google_appengine

CMD bash
