#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Archiver related exceptions."""


class ArchiverFieldError(Exception):
  """Exception class for field error.

  This exception is raised when field in configuration is invalid. Reasons
  are usually attached in the message.
  """
  pass
