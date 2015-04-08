#!/bin/sh
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This tool opens a local SSH port-forwarding tunnel to the Chrome remote
# debugging port on the specified DUT.


usage() {
  echo "Usage: ${0} hostname [local_port]"
}

get_debugging_port() {
  local dut="$1"
  echo $(ssh root@${dut} "ps -ef | grep -Eo 'debugging-port=[0-9]+' | uniq | \
      cut -d '=' -f 2" 2>/dev/null)
}

main() {
  local dut="$1"
  local local_port="$2"

  if [ -z "${dut}" ]; then
    usage
    exit 1
  fi

  if [ -z "${local_port}" ]; then
    local_port=8888
  fi

  echo "Trying to locate the remote debugging port on ${dut}..."
  local remote_port=
  while true; do
    remote_port="$(get_debugging_port ${dut})"
    if [ -n "${remote_port}" ]; then
      break
    fi
    sleep 1
  done
  echo "Got remote debugging port: ${remote_port}"

  echo "Create SSH tunnel ${local_port}:localhost:${remote_port} to ${dut}"
  local ssh_cmd="ssh -Nf -L ${local_port}:localhost:${remote_port} root@${dut}"
  sh -c "${ssh_cmd}"
  local ssh_pid="$(ps -ef | grep "${ssh_cmd}" | grep -v "grep" | \
      awk '{print $2}')"
  echo "PID of SSH tunnel: ${ssh_pid}"

  trap "echo 'SIGINT received, stopping tunnel...'; kill ${ssh_pid}; exit" SIGINT

  while [ -n "$(get_debugging_port ${dut})" ]; do
    sleep 1
  done
  echo "Remote debugging port is closed on ${dut}. Stopping SSH tunnel..."
  kill ${ssh_pid}
}

main $@
