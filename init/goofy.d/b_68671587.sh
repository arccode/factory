#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# http://b/68671587: Prevent TPM pre-initialization.

main() {
  mkdir -p /run/tpm_manager
  touch /run/tpm_manager/no_preinit
}

main "$@"
