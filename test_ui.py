#!/usr/bin/python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import threading

from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory.event import Event, EventClient


class FactoryTestFailure(Exception):
    pass


class UI(object):
    '''Web UI for a Goofy test.'''
    def __init__(self):
        self.lock = threading.RLock()
        self.event_client = EventClient(callback=self._handle_event)
        self.test = os.environ['CROS_FACTORY_TEST_PATH']
        self.invocation = os.environ['CROS_FACTORY_TEST_INVOCATION']
        self.event_handlers = {}

    def set_html(self, html):
        '''Sets the UI in the test pane.'''
        self.event_client.post_event(Event(Event.Type.SET_HTML,
                                           test=self.test,
                                           invocation=self.invocation,
                                           html=html))

    def run_js(self, js, **kwargs):
        '''Runs JavaScript code in the UI.

        Args:
            js: The JavaScript code to execute.
            kwargs: Arguments to pass to the code; they will be
                available in an "args" dict within the evaluation
                context.

        Example:
            ui.run_js('alert(args.msg)', msg='The British are coming')
        '''
        self.event_client.post_event(Event(Event.Type.RUN_JS,
                                           test=self.test,
                                           invocation=self.invocation,
                                           js=js, args=kwargs))

    def call_js_function(self, name, *args):
        '''Calls a JavaScript function in the test pane.

        Args:
            name: The name of the function to execute.
            args: Arguments to the function.
        '''
        self.event_client.post_event(Event(Event.Type.CALL_JS_FUNCTION,
                                           test=self.test,
                                           invocation=self.invocation,
                                           name=name, args=args))

    def add_event_handler(self, subtype, handler):
        '''Adds an event handler.

        Args:
            subtype: The test-specific type of event to be handled.
            handler: The handler to invoke with a single argument (the event
                object).
        '''
        self.event_handlers.setdefault(subtype, []).append(handler)

    def run(self):
        '''Runs the test UI, waiting until the test completes.'''
        event = self.event_client.wait(
            lambda event: event.type == Event.Type.END_TEST)
        logging.info('Received end test event %r', event)
        self.event_client.close()

        if event.status == TestState.PASSED:
            pass
        elif event.status == TestState.FAILED:
            raise FactoryTestFailure(event.error_msg)
        else:
            raise ValueError('Unexpected status in event %r' % event)

    def _handle_event(self, event):
        '''Handles an event sent by a test UI.'''
        if (event.type == Event.Type.TEST_UI_EVENT and
            event.test == self.test and
            event.invocation == self.invocation):
            with self.lock:
                for handler in self.event_handlers.get(event.subtype, []):
                    handler(event)
