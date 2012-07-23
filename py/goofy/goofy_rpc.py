#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''RPC methods exported from Goofy.'''

import inspect


class GoofyRPC(object):
  def __init__(self, goofy):
    self.goofy = goofy

  def RegisterMethods(self, state_instance):
    '''Registers exported RPC methods in a state object.'''
    for name, m in inspect.getmembers(self):
      # Find all non-private methods (except this one)
      if ((not inspect.ismethod(m)) or
          name.startswith('_') or
          name == 'RegisterMethods'):
        continue

      # Bind the state instance method to our method.  (The _m=m
      # argument is necessary to bind m immediately, since m will
      # change during the next for loop iteration.)
      state_instance.__dict__[name] = (
          lambda _m=m, *args, **kwargs: _m(*args, **kwargs))

  def FlushEventLogs(self):
    '''Flushes event logs if an event_log_watcher is available.

    Raises an Exception if syncing fails.
    '''
    self.goofy.log_watcher.FlushEventLogs()
