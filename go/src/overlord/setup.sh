#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -e

# This is a simple setup script that would interactively setup login
# credential and SSL certificate for Overlord.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
CONFIG_DIR="${SCRIPT_DIR}/config"

setup_login() {
  htpasswd_path="${CONFIG_DIR}/overlord.htpasswd"

  echo "Setting up Overlord login credentials."
  echo "This username / password would be used to login to overlord" \
    "web interface."
  echo

  printf "Enter username: "
  read -r username

  htpasswd -B -c "${htpasswd_path}" "${username}"

  # Create a special account for ovl tool.
  ovl_password=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 15)
  echo "${ovl_password}" > "${CONFIG_DIR}/ovl_password"
  htpasswd -b -B "${htpasswd_path}" "ovl" "${ovl_password}"

  echo "Login credentials for user ${username} is added."
}

setup_ssl() {
  ca_key_path="${CONFIG_DIR}/rootCA.key"  # root CA private key
  ca_cert_path="${CONFIG_DIR}/rootCA.pem"  # root CA certificate
  ca_sign_request_path="${CONFIG_DIR}/CA.csr"
  ext_conf_path="${CONFIG_DIR}/conf.ext"  # CA ext conf
  key_path="${CONFIG_DIR}/key.pem"  # Private key
  cert_path="${CONFIG_DIR}/cert.pem"  # Certificate signed by root CA

  echo "Setting up Overlord SSL certificates."
  echo

  printf "Enter the FQDN / IP for the server running Overlord: "
  read -r common_name

  # We can only assign ip to IP attribute.
  if expr "${common_name}" : \
    '[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$' >/dev/null; then
    ip_setting="IP.2 = ${common_name}"
  fi

  openssl genrsa -out "${ca_key_path}"
  openssl req -x509 -new -nodes -key "${ca_key_path}" -sha256 -days 3650 \
    -out "${ca_cert_path}" -subj "/CN=Google ChromeOS Factory"

  openssl genrsa -out "${key_path}"
  openssl req -new -key "${key_path}" -out "${ca_sign_request_path}" \
    -subj "/CN=${common_name}"

  >"${ext_conf_path}" cat <<-EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = ${common_name}
IP.1 = 127.0.0.1
${ip_setting}
EOF

  openssl x509 -req -in "${ca_sign_request_path}" -CA "${ca_cert_path}" \
    -CAkey "${ca_key_path}" -CAcreateserial -out "${cert_path}" -days 365 \
    -sha256 -extfile "${ext_conf_path}"
}

main() {
  setup_login
  echo

  if [ "$1" = "skip_ssl_setting" ]
  then
    return
  fi
  setup_ssl
}

main "$@"
