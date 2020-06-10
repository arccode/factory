# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM python:2.7

ARG workdir="/usr/src/"
ARG gcloud_archive_name="google-cloud-sdk-245.0.0-linux-x86_64.tar.gz"

ADD factory/py/hwid/service/appengine/requirements.txt \
  "${workdir}"/requirements.txt

RUN cd "${workdir}" && \
  wget "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${gcloud_archive_name}" && \
  tar xvf "${gcloud_archive_name}" && \
  apt update && apt install -y redis-server openjdk-11-jre && \
  google-cloud-sdk/install.sh \
    --rc-path /root/.bashrc \
    --additional-components app-engine-python app-engine-python-extras beta \
    --quiet && \
  rm "${gcloud_archive_name}" && \
  pip install \
    --target "${workdir}"/lib \
    --requirement "${workdir}"/requirements.txt \
    mox==0.5.3 \
    mock==2.0.0 \
    protorpc-standalone==0.9.1 \
    PyYaml==3.11 \
    webapp2==3.0.0b1 \
    WebTest==2.0.29

ADD factory/py "${workdir}/cros/factory/py"
ADD factory/py_pkg "${workdir}/cros/factory/py_pkg"
ADD chromeos-hwid/py "${workdir}/cros/chromeos-hwid/py"
ADD factory/build/hwid/protobuf_out "${workdir}/protobuf_out"
ADD factory-private/config/hwid/service/appengine/configurations.yaml \
  "${workdir}/resource/"

ENV PYTHONPATH="${workdir}/lib:"\
"${workdir}/google-cloud-sdk/platform/google_appengine:"\
"${workdir}/protobuf_out:"\
"${workdir}/cros/factory/py_pkg"
ENV HWID_SERVICE_RESOURCE_DIR="${workdir}/resource"
ENV CUSTOMIZE_SITE_DIR="${workdir}/lib"
ENV DATASTORE_EMULATOR_HOST="localhost:8081"
ENV CLOUDSDK_CORE_PROJECT="chromeos-hwid-local-docker"

CMD redis-server & \
  /usr/src/google-cloud-sdk/bin/gcloud beta emulators datastore \
  start --consistency=1 & bash
