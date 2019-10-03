# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sphinx extension for preprocessing factory docs."""

import re

from docutils import nodes
from docutils.parsers.rst import Directive

from cros.factory.test.l10n import regions


class regionslist(nodes.General, nodes.Element):
  # pylint: disable=no-init
  pass


class unconfirmed_regionslist(nodes.General, nodes.Element):
  # pylint: disable=no-init
  pass


class RegionsList(Directive):
  """List of regions from the regions and regions_overlay modules."""
  # pylint: disable=no-init
  has_content = True
  required_arguments = 0
  optional_arguments = 0
  option_spec = {}
  list_name = 'REGIONS_LIST'
  table_classes = ['factory-regions-list']

  def run(self):
    # Create the header row.
    thead_row = nodes.row('')
    column_names = (
        'Description', 'Region Code', 'Keyboard', 'Time Zone', 'Lang.',
        'Layout', 'Notes')
    # Make the "Notes" field a bit wider.
    column_widths = (1, 1, 1, 1, 1, 1, 2)
    for column in column_names:
      thead_row += nodes.entry('', nodes.paragraph('', column))

    # Create the body.
    tbody = nodes.tbody('')

    # Import the regions_overlay if available.
    try:
      # pylint: disable=no-name-in-module
      from cros.factory.test.l10n import regions_overlay
      overlay = regions_overlay
    except ImportError:
      overlay = None

    name = self.list_name
    # For both the public repo and the overlay...
    for module in filter(None, [regions, overlay]):
      # For each of the elements in the list...
      for r in sorted(getattr(module, name), key=lambda x: x.description):
        # Build a row.
        row = nodes.row('')

        row += nodes.entry('', nodes.paragraph(
            '', r.description, classes=['description']))

        # For each of the columns...
        for value in [r.region_code,
                      ', '.join(r.keyboards),
                      r.time_zone,
                      ', '.join(r.language_codes),
                      str(r.keyboard_mechanical_layout)]:
          text = nodes.paragraph('', value)
          row += nodes.entry('', text)

        # 'notes' column is very special.
        notes = r.notes or ''
        if notes:
          short_notes = notes if len(notes) < 20 else (notes[:20] + '...')
          row += nodes.entry(
              '', nodes.paragraph('', short_notes, classes=['note']),
              nodes.paragraph('', notes, classes=['spnTooltip']))
        else:
          row += nodes.entry('')
        tbody += row

    tgroup = nodes.tgroup('')
    tgroup += [nodes.colspec(colwidth=x) for x in column_widths]
    tgroup += nodes.thead('', thead_row)
    tgroup += tbody

    return [nodes.table('', tgroup, classes=self.table_classes)]


class UnconfirmedRegionsList(RegionsList):
  # pylint: disable=no-init
  list_name = 'UNCONFIRMED_REGIONS_LIST'
  table_classes = ['factory-regions-list factory-unconfirmed-regions-list']


def ProcessDocstring(unused_app, what, unused_name, unused_obj,
                     unused_options, lines):
  """Hook to process docstrings.

  We use this to munge the docstrings so that they can both match the
  Chromium Python Style Guide and still be valid reStructuredText.  In
  particular, we change sections like this::

    Args:
      some_argument: This is a description of
        an argument.

    Returns:
      Description of return value.

  to::

    :param some_argument: This is a description of
        an argument.

    :return:
       Description of return value.
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

      if line == 'Returns:':
        line = ':return:'

      if in_section == 'Args':
        # Within the "Args" section, use the :param tag for each
        # argument.
        line = re.sub(r'^  (\S+):', r':param \1:', line)

      lines[i] = line


def setup(app):
  app.connect('autodoc-process-docstring', ProcessDocstring)

  app.add_node(regionslist)
  app.add_node(unconfirmed_regionslist)
  app.add_directive('regionslist', RegionsList)
  app.add_directive('unconfirmed_regionslist', UnconfirmedRegionsList)
