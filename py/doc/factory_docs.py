# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sphinx extension for preprocessing factory docs."""

import re

from docutils import nodes
from sphinx.util.compat import Directive

import factory_common  # pylint: disable=W0611
from cros.factory.l10n import regions


class regionslist(nodes.General, nodes.Element):
  # pylint: disable=W0232
  pass


class RegionsList(Directive):
  """List of regions from the regions and regions_overlay modules."""
  has_content = True
  required_arguments = 0
  optional_arguments = 0
  option_spec = {}

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
      from cros.factory.l10n import regions_overlay  # pylint: disable=E0611
      overlay = regions_overlay
    except ImportError:
      overlay = None

    # For each of the possible names of an attribute containing the
    # region information... (we add a '?' to fields for unconfirmed regions,
    # '??' for incomplete regions)
    for name, confirmed, suffix in (
      ('REGIONS_LIST', True, ''),
      ('UNCONFIRMED_REGIONS_LIST', False, '?'),
      ('INCOMPLETE_REGIONS_LIST', False, '??')):
      # For both the public repo and the overlay...
      for module in filter(None, [regions, overlay]):
        # For each of the elements in the list...
        for r in sorted(getattr(module, name),
                        key=lambda x: x.description):
          # Build a row.
          row = nodes.row('')

          # Add an asterisk to description/region code for
          # regions from the overlay.
          overlay_suffix = (
            '*' if module == overlay else '')

          # For each of the columns...
          for value in [r.description + overlay_suffix,
                        r.region_code + overlay_suffix,
                        ', '.join(r.keyboards),
                        r.time_zone,
                        ', '.join(r.language_codes),
                        str(r.keyboard_mechanical_layout),
                        r.notes or '']:
            if value:
              value += suffix

            if confirmed:
              text = nodes.paragraph('', value)
            else:
              # Italic (since it's not confirmed).
              text = nodes.emphasis('', value)
            row += nodes.entry('', text)
          tbody += row

    tgroup = nodes.tgroup('')
    tgroup += [nodes.colspec(colwidth=x) for x in column_widths]
    tgroup += nodes.thead('', thead_row)
    tgroup += tbody

    return [nodes.table('', tgroup, classes=['factory-small'])]


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

  app.add_node(regionslist)
  app.add_directive('regionslist', RegionsList)

