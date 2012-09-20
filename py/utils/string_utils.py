#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


def DecodeUTF8(data):
  '''Decodes data as UTF-8, replacing any bad characters.'''
  return unicode(data, encoding='utf-8', errors='replace')

def CleanUTF8(data):
  '''Returns a UTF-8-clean string.'''
  return DecodeUTF8(data).encode('utf-8')
