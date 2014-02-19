Regional Configuration
======================

Like most operating systems, CrOS supports user-selectable region
settings, including keyboard layouts, languages, and time zones.  In
order to support an ideal out-of-box experience (OOBE), each device
must be shipped with regional configuration suitable for its intended
users.  These settings are stored in the RO VPD (read-only vital
product data) in the ``initial_locale``, ``keyboard_layout``, and
``initial_timezone`` fields.

This document describes how regional configurations are managed in the
factory SDK.

.. _region-codes:

Regions and region codes
------------------------
A **region** is a market in which shipped devices share a particular
configuration of keyboard layout, language, and time zone.

Each region is identified with a **region code** such as ``us``.  A region
may be any of the following:

* A single country, such as the United States.  The region code is the
  two-letter `ISO 3166-1 alpha-2 code
  <http://en.wikipedia.org/wiki/ISO_3166-1_alpha-2>`_, e.g., ``us``.
  Note that the alpha-2 code for the UK is ``gb``, not ``uk``.

* A non-country entity, such as Hong Kong, that has an ISO 3166-1
  alpha-2 code assigned. The region code is the two-letter ISO 3166-1
  alpha-2 code, e.g., ``hk``.

* A collection of countries or entities that share a regional
  configuration, such as Hispanophone Latin American countries
  (including Mexico, Colombia, Argentina, Peru, etc.) or Nordic
  countries.  The region code is a unique identifier (>3 characters to
  avoid conflict with ISO alpha codes), e.g., ``latam-es-419`` or
  ``nordic``.

* Part of a country or entity that has a specific regional
  configuration, e.g., Francophone Canada.  The region code is one of
  the region codes described above, plus a period (``.``), plus an
  identifier describing the variant.  For example, Francophone
  Canada's region code is ``ca.fr``.

Note that the concepts of regions and region codes, in the sense they
are used in this document, are specific to the factory SDK.  There is
no single accepted worldwide standard for setting region
configurations.

Currently, the region code is not directly used anywhere in CrOS; it
is solely an identifier used by the factory flow to identify the
shipping market for a device.  However, in the future it may be used
in CrOS (e.g., to enable or disable functionality for certain markets
for regulatory reasons).

The :py:class:`cros.factory.l10n.regions.Region` [#l10n]_ class encapsulates a
single regional configuration.

.. _available-regions:

Available regions
-----------------
Following is a table of known regions.  Incomplete and unconfirmed
regions (not ready for use in shipping products) are italicized and
marked with question marks; if you need to use one of these please see
http://goto/vpdsettings for review.

For more information on what each field means and what the valid
values are, see :py:class:`cros.factory.l10n.regions.Region`.

.. warning::

  Concrete VPD values (keyboard, time zone, language, etc.) in this
  table are provided for reference only; they are not intended to be
  copied-and-pasted from this table into shop floor servers.  Rather,
  shop floor servers should provide only the region code for the
  device, and the ``vpd`` test should be used to populate the concrete
  VPD values based on values in the codebase.  See
  :ref:`region-factory-flow`.

.. warning::

  Launch plans for regions marked with asterisks, if any, may not be
  publicly known.  Take caution when sharing these values.  These
  regions are stored in the `private repository
  <http://goto/private-regions>`_, and to use one of these you will
  need to create a ``regions_overlay.py`` in your board overlay.


.. regionslist::

How VPD values affect the CrOS user experience
----------------------------------------------
See http://goto/vpdsettings.

Selecting values for new regions
--------------------------------
If you need to add a new region, see
:py:class:`cros.factory.l10n.regions.Region` for information on how to
select the concrete VPD values for keyboard, time zone, and language.
The class documentation provides links to pages that provide sets of
values to choose from.

See :ref:`where-regions-are-defined` for information on where to add
the new region to the codebase.

.. _region-factory-flow:

How regions are set in the factory flow
---------------------------------------

In general, the test list should contain an invocation of the
``call_shopfloor`` test with the ``update_device_data`` action to
obtain the region code from the shop floor server, and set the
``region_code`` value in the device data dictionary.  For instance::

    OperatorTest(
        id='GetDeviceInfo',
        pytest_name='call_shopfloor',
        dargs=dict(
            method='GetDeviceInfo',
            args=lambda env: [
                env.GetDeviceData()['mlb_serial_number'],
                ],
            action='update_device_data'))

The ``vpd`` test can then be used to read the ``region_code`` entry
from the device data dictionary, look up the necessary VPD fields
(``initial_locale``, ``keyboard_layout``, and ``initial_timezone``),
and store the fields into the RO VPD.  In addition, the ``vpd`` test
also saves the region code into the ``region`` field in the RO VPD.
For example::

    OperatorTest(
        id='VPD',
        dargs=dict(use_shopfloor_device_data=True,
                   allow_multiple_l10n=False))

.. warning::

   Multiple keyboards and initial locales are only supported in M34+.
   For this reason, the VPD test defaults to
   ``allow_multiple_l10n=False``, in which case only the first
   keyboard and initial locale will be used for OOBE.  To allow
   multiple localizations once M34 is being shipped on device, set
   ``allow_multiple_l10n=True``.

.. warning::

   The precise values of these VPD fields (e.g.,
   ``keyboard_layout=xkb:us::eng``) should *not* be retrieved directly
   on the shop floor server, since it is an error-prone process to
   store the correct VPD values for all valid regions on individual
   projects' shop floor servers.  Rather, the appropriate region code
   should be retrieved from the shop floor server and the ``vpd`` test
   should be used to set the precise VPD field values.  This ensures
   that the VPD field values are consistent and up to date.

Region API
----------

.. py:module:: cros.factory.l10n.regions

.. autoclass:: Region
   :members:

The :py:func:`cros.factory.l10n.regions.BuildRegionsDict` method is
used to obtain a list of all confirmed regions.  In general, code
should not invoke this directly but rather use
:py:data:`cros.factory.l10n.regions.REGIONS`.

.. autofunction:: BuildRegionsDict

.. autodata: REGIONS

.. _where-regions-are-defined:

Where regions are defined
~~~~~~~~~~~~~~~~~~~~~~~~~

The complete set of confirmed regions (regions available for use in
shipping products) is specified by
:py:data:`cros.factory.l10n.regions.REGIONS_LIST`.

.. autodata:: cros.factory.l10n.regions.REGIONS_LIST

In addition, there are two module-level attributes used to accumulate
region configuration settings that are thought to be correct but have
not been completely verified yet.

.. autodata:: cros.factory.l10n.regions.UNCONFIRMED_REGIONS_LIST

.. autodata:: cros.factory.l10n.regions.INCOMPLETE_REGIONS_LIST

If you cannot add a region to the public factory repository, you may
add it to the ``cros.factory.l10n.regions_overlay`` module, in one of
the following attributes:

* ``cros.factory.l10n.regions_overlay.REGIONS_LIST``
* ``cros.factory.l10n.regions_overlay.UNCONFIRMED_REGIONS_LIST``
* ``cros.factory.l10n.regions_overlay.INCOMPLETE_REGIONS_LIST``

There is a reference list of "private" regions, suitable for addition
to board overlays, in the ``factory-private`` repository
(http://goto/private-regions).

.. rubric:: Footnotes

.. [#l10n] "l10n" is a common abbreviation for "localization": "l",
   plus 10 letters "ocalization", plus "n".)

