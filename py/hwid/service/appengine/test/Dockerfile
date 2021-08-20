# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM python:3.7

ARG workdir="/usr/src/"
ARG gcloud_archive_name="google-cloud-sdk-353.0.0-linux-x86_64.tar.gz"

RUN cd "${workdir}" && \
  wget "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${gcloud_archive_name}" && \
  tar xvf "${gcloud_archive_name}" && \
  apt update && apt install -y redis-server openjdk-11-jre && \
  google-cloud-sdk/install.sh \
    --rc-path /root/.bashrc \
    --additional-components app-engine-python app-engine-python-extras beta \
    --quiet && \
  rm "${gcloud_archive_name}"

ADD requirements.txt "${workdir}/requirements.txt"

RUN pip install \
      --target "${workdir}"/lib \
      --requirement "${workdir}"/requirements.txt

ADD . "${workdir}/hwid"

ENV PYTHONPATH="${workdir}/lib:${workdir}/hwid"
ENV CUSTOMIZE_SITE_DIR="${workdir}/lib"
ENV CLOUDSDK_CORE_PROJECT="chromeos-hwid-local-docker"
ENV DATASTORE_DATASET="chromeos-hwid-local-docker"
ENV DATASTORE_EMULATOR_HOST="localhost:8081"
ENV DATASTORE_EMULATOR_HOST_PATH="localhost:8081/datastore"
ENV DATASTORE_HOST="http://localhost:8081"
ENV DATASTORE_PROJECT_ID="chromeos-hwid-local-docker"

CMD redis-server & \
  /usr/src/google-cloud-sdk/bin/gcloud beta emulators datastore \
  start --consistency=1 & bash
