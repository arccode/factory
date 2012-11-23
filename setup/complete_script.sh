#!/bin/sh

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a sample script to be executed after installation is completed.
# To use this script, run mini-omaha server using make_factory_package
# with --complete_script.

TTY="/dev/tty1"
printf "\033[1;32m" > "$TTY"
echo "" > "$TTY"
echo "                ######                     ######         ######" > "$TTY"
echo "          ##################               ######        ###### " > "$TTY"
echo "         ####################              ######       ######  " > "$TTY"
echo "       #########      #########            ######      ######   " > "$TTY"
echo "     ########            ########          ######     ######    " > "$TTY"
echo "    #######                #######         ######    ######     " > "$TTY"
echo "    ######                  ######         ######   ######      " > "$TTY"
echo "    ######                  ######         ######  ######       " > "$TTY"
echo "    ######                  ######         ###### ######        " > "$TTY"
echo "    ######                  ######         ############         " > "$TTY"
echo "    ######                  ######         ############         " > "$TTY"
echo "    ######                  ######         ############         " > "$TTY"
echo "    ######                  ######         ###### ######        " > "$TTY"
echo "    ######                  ######         ######  ######       " > "$TTY"
echo "    ######                  ######         ######   ######      " > "$TTY"
echo "    #######                #######         ######    ######     " > "$TTY"
echo "     ########            ########          ######     ######    " > "$TTY"
echo "       #########      #########            ######      ######   " > "$TTY"
echo "         ####################              ######       ######  " > "$TTY"
echo "          ##################               ######        ###### " > "$TTY"
echo "                ######                     ######         ######" > "$TTY"
echo "" > "$TTY"
echo "Factory image downloaded." > "$TTY"
echo -n "Press Enter to restart..." > "$TTY"
read DUMMY < "$TTY"
