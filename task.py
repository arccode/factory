#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# A library for factory tests with sub-tasks.


import logging
import collections

# GTK modules
import gobject
import gtk

import factory_common
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import ui


def schedule(task, *args, **kargs):
    """Schedules a task function to be executed one time in GTK context."""
    def idle_callback():
        task(*args, **kargs)
        return False
    gobject.idle_add(idle_callback)


class FactoryTask(object):
    """Base class for factory tasks."""

    TaskSession = collections.namedtuple(
            'TaskSession',
            'remover, on_stop, widgets, window_connects, timeout_callbacks')

    def _attach_to_task_manager(self, window, container, remover):
        """Attaches to a task manager.

        @param window: The window provided by task manager.
        @param container: Container widget inside window.
        @param remover: Callback to remove task.
        """
        assert not hasattr(self, "_task_session"), "Already attached before."
        self.window = window
        self.container = container
        self._task_session = self.TaskSession(remover, self.stop, [], [], [])
        # Hook self.stop
        self.stop = self._detach_from_task_manager

    def _detach_from_task_manager(self):
        assert hasattr(self, "_task_session"), "Not attached yet."
        self._task_session.on_stop()
        for callback in self._task_session.timeout_callbacks:
            gobject.source_remove(callback)
        for callback in self._task_session.window_connects:
            self.window.disconnect(callback)
        for widget in self._task_session.widgets:
            widget.hide()
            self.container.remove(widget)
        # Restore self.stop
        self.stop = self._task_session.on_stop
        remover = self._task_session.remover
        del self._task_session
        remover(self)

    def add_widget(self, widget):
        """Adds a widget to container (automatically removed on stop)."""
        self._task_session.widgets.append(widget)
        self.container.add(widget)
        # For widgets created by ui.make_input_window.
        if hasattr(widget, 'entry'):
            widget.entry.grab_focus()

    def connect_window(self, *args, **kargs):
        """Connects a window event (automatically cleared on stop)."""
        self._task_session.window_connects.append(
                self.window.connect(*args, **kargs))

    def add_timeout(self, *args, **kargs):
        """Adds a timeout callback (automatically deleted on stop)."""
        self._task_session.timeout_callbacks.append(
                gobject.timeout_add(*args, **kargs))

    def start(self):
        """The procedure for preparing widgets and threads."""
        logging.debug("%s: started.", self.__class__.__name__)

    def stop(self):
        """The procedure to notify task manager to terminate current task."""
        logging.debug("%s: stopped.", self.__class__.__name__)


def run_factory_tasks(job, tasklist, on_complete=gtk.main_quit):
    """Runs a list of factory tasks.

    @param job: The job object from autotest "test.job".
    @param tasklist: A list of FactoryTask objects to run.
    @param on_complete: Callback when no more tasks to run.
    """
    session = {}

    def find_next_task():
        if tasklist:
            task = tasklist[0]
            logging.info("Starting task: %s", task.__class__.__name__)
            task._attach_to_task_manager(session['window'], container,
                                         remove_task)
            task.start()
            container.show_all()
        else:
            # No more tasks - try to complete.
            logging.info("All tasks completed.")
            schedule(on_complete)
        return False

    def remove_task(task):
        factory.log("Stopping task: %s" % task.__class__.__name__)
        tasklist.remove(task)
        schedule(find_next_task)

    def register_window(window):
        session['window'] = window
        schedule(find_next_task)

    container = gtk.VBox()
    ui.run_test_widget(job, container,
                       window_registration_callback=register_window)
