# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sphinx extension for preprocessing factory docs."""

import re

import factory_common  # pylint: disable=W0611

def ProcessDocstring(dummy_app, what, dummy_name, dummy_obj,
                     dummy_options, lines):
  """Hook to process docstrings.

  We use this to munge the docstrings so that they can both match the
  Chromium Python Style Guide and still be valid reStructuredText.  In
  particular, we change sections like this::

    Args:
      some_argument: This is a description of
        an argument.

  to::

    :param some_argument: This is a description of
        an argument.
  """
  if what in ['function', 'method']:
    # Remember which section we're in (like "Args").
    in_section = None

    for i, line in enumerate(lines):
      match = re.match(r'^(\w+):$', line)
      if match:
        in_section = match.group(1)

      if line == 'Args:':
        # Remove this line (we'll use the :param keyword for each
        # individual argument).
        line = ''

      if in_section == 'Args':
        # Within the "Args" section, use the :param tag for each
        # argument.
        line = re.sub(r'^  (\S+):', r':param \1:', line)

      lines[i] = line


def setup(app):
  app.connect('autodoc-process-docstring', ProcessDocstring)

