#!/bin/sh

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a sample script to be executed after installation is completed.
# To use this script, run mini-omaha server using make_factory_package
# with --complete_script.

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
echo "Factory image downloaded."
printf "Press Enter to restart... "
head -c 1 >/dev/null
