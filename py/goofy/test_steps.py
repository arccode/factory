# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
Test steps run directly within Goofy.
'''

import logging

import factory_common
from cros.factory.test import factory
from cros.factory.test.factory import FactoryTest


class FlushEventLogsStep(FactoryTest):
    '''Synchronizes event logs.'''
    def __init__(self, **kw):
        super(FlushEventLogsStep, self).__init__(invocation_target=self._Run,
                                                 _default_id='FlushEventLogs')

    def _Run(self, invocation):
        log_watcher = invocation.goofy.log_watcher
        # Display a message on the console if we're going to need to wait
        if log_watcher.IsScanning():
            factory.console.info('Waiting for current scan to finish...')
        factory.console.info('Flushing event logs...')
        log_watcher.FlushEventLogs()
        factory.console.info('Flushed event logs.')
