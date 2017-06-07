#!/bin/sh
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is the default script to be executed after imaging process is completed.
# A factory bundle created by 'finalize_bundle' will automatically include and
# use this file. To override, create a script file in
# chromeos-base/factory-board/${FILESDIR}/bundle/complete in private board
# overlay.

printf "\033[1;32m"
echo ""
echo "                ######                     ######         ######"
echo "          ##################               ######        ###### "
echo "         ####################              ######       ######  "
echo "       #########      #########            ######      ######   "
echo "     ########            ########          ######     ######    "
echo "    #######                #######         ######    ######     "
echo "    ######                  ######         ######   ######      "
echo "    ######                  ######         ######  ######       "
echo "    ######                  ######         ###### ######        "
echo "    ######                  ######         ############         "
echo "    ######                  ######         ############         "
echo "    ######                  ######         ############         "
echo "    ######                  ######         ###### ######        "
echo "    ######                  ######         ######  ######       "
echo "    ######                  ######         ######   ######      "
echo "    #######                #######         ######    ######     "
echo "     ########            ########          ######     ######    "
echo "       #########      #########            ######      ######   "
echo "         ####################              ######       ######  "
echo "          ##################               ######        ###### "
echo "                ######                     ######         ######"
echo ""
echo "Factory images downloaded and installed."
printf "Press Enter to restart... "
head -c 1 >/dev/null
