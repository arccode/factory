#!/usr/bin/python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import threading
import traceback

from cros.factory.test import factory
from cros.factory.test.factory import TestState
from cros.factory.test.event import Event, EventClient


class FactoryTestFailure(Exception):
    pass


class UI(object):
    '''Web UI for a Goofy test.

    You can set your test up in the following ways:

    1. For simple tests with just Python+HTML+JS:

         mytest.py
         mytest.js    (automatically loaded)
         mytest.html  (automatically loaded)

       This works for autotests too:

         factory_MyTest.py
         factory_MyTest.js    (automatically loaded)
         factory_MyTest.html  (automatically loaded)

    2. If you have more files to include, like images
       or other JavaScript libraries:

         mytest.py
         mytest_static/
           mytest.js           (automatically loaded)
           mytest.html         (automatically loaded)
           some_js_library.js  (NOT automatically loaded;
                                use <script src="some_js_lib.js">)
           some_image.gif      (use <img src="some_image.gif">)

    3. Same as #2, but with a directory just called "static" instead of
       "mytest_static".  This is nicer if your test is already in a
       directory that contains the test name (as for autotests).  So
       for a test called factory_MyTest.py, you might have:

         factory_MyTest/
           factory_MyTest.py
           static/
             factory_MyTest.html  (automatically loaded)
             factory_MyTest.js    (automatically loaded)
             some_js_library.js
             some_image.gif

    Note that if you rename .html or .js files during development, you
    may need to restart the server for your changes to take effect.
    '''
    def __init__(self):
        self.lock = threading.RLock()
        self.event_client = EventClient(callback=self._handle_event)
        self.test = os.environ['CROS_FACTORY_TEST_PATH']
        self.invocation = os.environ['CROS_FACTORY_TEST_INVOCATION']
        self.event_handlers = {}

        # Set base URL so that hrefs will resolve properly,
        # and pull in Goofy CSS.
        self.append_html('\n'.join([
                    '<base href="/tests/%s/">' % self.test,
                    ('<link rel="stylesheet" type="text/css" '
                     'href="/goofy.css">')]))
        self._setup_static_files(
            os.path.realpath(traceback.extract_stack()[-2][0]))

    def _setup_static_files(self, py_script):
        # Get path to caller and register static files/directories.
        base = os.path.splitext(py_script)[0]

        # Directories we'll autoload .html and .js files from.
        autoload_bases = [base]

        # Find and register the static directory, if any.
        static_dirs = filter(os.path.exists,
                             [base + '_static',
                              os.path.join(os.path.dirname(py_script), 'static')
                             ])
        if len(static_dirs) > 1:
            raise FactoryTestFailure('Cannot have both of %s - delete one!' %
                                     static_dirs)
        if static_dirs:
            factory.get_state_instance().register_path(
                '/tests/%s' % self.test, static_dirs[0])
            autoload_bases.append(
                os.path.join(static_dirs[0], os.path.basename(base)))

        # Autoload .html and .js files.
        for extension in ('js', 'html'):
            autoload = filter(os.path.exists,
                              [x + '.' + extension
                               for x in autoload_bases])
            if len(autoload) > 1:
                raise FactoryTestFailure(
                    'Cannot have both of %s - delete one!' %
                    autoload)
            if autoload:
                factory.get_state_instance().register_path(
                    '/tests/%s/%s' % (self.test, os.path.basename(autoload[0])),
                    autoload[0])
                if extension == 'html':
                    self.append_html(open(autoload[0]).read())
                else:
                    self.append_html('<script src="%s"></script>' %
                                     os.path.basename(autoload[0]))

    def set_html(self, html, append=False):
        '''Sets the UI in the test pane.'''
        self.event_client.post_event(Event(Event.Type.SET_HTML,
                                           test=self.test,
                                           invocation=self.invocation,
                                           html=html,
                                           append=append))

    def append_html(self, html):
        '''Append to the UI in the test pane.'''
        self.set_html(html, True)

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

        This will be run within window scope (i.e., 'this' will be the
        test pane window).

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

    def url_for_file(self, path):
        '''Returns a URL that can be used to serve a local file.

        Args:
          path: path to the local file

        Returns:
          url: A (possibly relative) URL that refers to the file
        '''
        return factory.get_state_instance().url_for_file(path)

    def url_for_data(self, mime_type, data, expiration=None):
        '''Returns a URL that can be used to serve a static collection
        of bytes.

        Args:
          mime_type: MIME type for the data
          data: Data to serve
          expiration_secs: If not None, the number of seconds in which
            the data will expire.
        '''
        return factory.get_state_instance().url_for_data(
            mime_type, data, expiration)

    def run(self):
        '''Runs the test UI, waiting until the test completes.'''
        event = self.event_client.wait(
            lambda event:
                (event.type == Event.Type.END_TEST and
                 event.invocation == self.invocation and
                 event.test == self.test))
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
