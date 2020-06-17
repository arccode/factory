Regional Configuration
======================

Like most operating systems, CrOS supports user-selectable region
settings, including keyboard layouts, languages, and time zones.  In
order to support an ideal out-of-box experience (OOBE), each device
must be shipped with regional configuration suitable for its intended
users.  These settings are controlled by a value stored in the RO VPD (read-only
vital product data) `region` field, and a database `cros-regions.json`.

This document describes how regional configurations are managed in the
factory SDK.

.. contents::
   :local:

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

Currently, the region code is used by CrOS to derive regional data, for example
locales or Wi-Fi regulatory domain. The regional data can be updated, but the
region code itself is locked in VPD RO area.

The :py:class:`cros.factory.test.l10n.regions.Region` [#l10n]_ class
encapsulates a single regional configuration.

.. _available-regions:

Available regions
-----------------
Following is a table of known regions. If you need a new region, please first
check the "Unconfirmed regions" section below.

.. warning::

  Concrete VPD values (keyboard, time zone, language, etc.) in this
  table are provided for reference only; they are not intended to be
  copied-and-pasted from this table into shop floor servers.  Rather,
  shop floor servers should provide only the region code for the
  device. See :ref:`region-factory-flow`.

.. regionslist::

Unconfirmed regions
-------------------
Following is a table of unconfirmed regions  (not ready for use in shipping
products). If you need to use one of these please see http://goto/vpdsettings
and src/platform2/regions/README for how to proceed.

For more information on how to choose field values, see
:ref:`regions-values`.

.. unconfirmed_regionslist::

How VPD values affect the CrOS user experience
----------------------------------------------
See http://goto/vpdsettings.

.. _regions-values:

Selecting values for new regions
--------------------------------
When adding a new region, you must choose the appropriate values
for each field. This section describes how to choose these values.

Note that two fields (``keyboards`` and ``language_codes``) are lists,
while the others are strings. When declaring regions with multiple
keyboards or language codes, make sure to use a Python list (e.g.,
``['en', 'fr']``) for those fields and not a comma-separated string (e.g.,
``'en,fr'``). The values are ultimately encoded as a comma-separated
string in the VPD, but in the regions database they are represented as
Python lists.

The exact set of values supported by CrOS, naturally, depends on the
CrOS image that will be installed. For instance, multiple keyboards
and language codes are supported only in M34+, and input methods other
than ``xkb:...`` are supported only in M38+. Always test your
region settings to make sure they work as you expect on the CrOS image
that will be used (see :ref:`regions-testing`).

Region code
~~~~~~~~~~~
See :ref:`region-codes` for information about region codes.

This field is stored in the VPD but is not currently used by CrOS.

.. _regions-keyboards:

Keyboard layouts (input methods)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``keyboards`` field is a list of input method IDs. The first one is the
default. In general these should correspond to the languages chosen;
when a language is selected, only keyboards that represent a valid
choice for that language are shown.

Each identifier must start with either ``xkb:`` or ``m17n:`` or
``ime:``.  As of M38, valid keyboard layout identifiers are:

- ``xkb:...``: XKB input methods listed in any file in JSON files in
  the Chromium `src/chrome/browser/resources/chromeos/input_method
  <http://goo.gl/z4JGvK>`_ directory. (Look for the ``id`` attributes
  of each ``input_components`` list entry.)  For example, you will
  find ``xkb:us::eng`` in `google_xkb_manifest.json
  <http://goo.gl/jBtjIV>`_.

- ``ime:...``: (M38+ only) Any hard-coded strings listed in
  ``kEngineIdMigrationMap`` in Chromium's `input_method_util.cc
  <http://goo.gl/cDO53r>`_. Currently this is:

    - ``ime:zh-t:quick``
    - ``ime:zh-t:pinyin`` (not yet supported as of this writing, but
      should be added in M38)
    - ``ime:ko:hangul``
    - ``ime:ko:hangul_2set``

- ``m17n:...``: (M38+ only) Strings with a prefix in
  ``kEngineIdMigrationMap``. The prefix is rewritten according to
  the map, and there must be a corresponding input method ID in some
  file in the ``input_method`` directory. For instance, ``m17n:ar`` will
  be rewritten to ``vkd_ar`` according to the map.  ``vkd_ar`` is
  present in ``google_input_tools_manifest.js``.

Since a Latin keyboard is required for login, the first entry in this
list should be a Latin layout corresponding to the first language in
the ``language_codes`` field. If that language has a non-Latin
keyboard, then ``xkb:us::eng`` should be used as the first entry.

See :ref:`where-regions-are-defined` for information on where to add
the new region to the codebase.

.. _regions-time-zone:

Time zone
~~~~~~~~~
The ``time_zone`` field specifies a single time zone that will be used as the
default timezone. M35+ supports automatic time zone detection based on
geolocation, but it is still worthwhile to choose a reasonable default
time zone default.

This must be a `tz database time zone
<http://en.wikipedia.org/wiki/List_of_tz_database_time_zones>`_
identifier (e.g., ``America/Los_Angeles``). See `timezone_settings.cc
<http://goo.gl/WSVUeE>`_ for supported time zones.

There is no hard-and-fast rule for selecting the time zone, but as a
rule of thumb, you can choose the city representing the time zone in
the region with the largest population.

.. _region-factory-flow:

Language codes
~~~~~~~~~~~~~~
The ``language_codes`` field  is a list of language codes. See the
``kAcceptLanguageList`` array in `l10n_util.cc <http://goo.gl/kVkht>`_
for supported languages.

Keyboard mechanical layout
~~~~~~~~~~~~~~~~~~~~~~~~~~
This describes the shape of keys. It is used only to display an appropriate
keyboard onscreen during the keyboard test; it is not stored in the VPD
or used by Chrome OS. This may be one of:

- ``ANSI`` for ANSI (US-like) keyboard layouts with a horizontal Enter key.
- ``ISO`` for ISO (UK-like) keyboard layouts with a vertical Enter key.
- ``JIS`` for the JIS (Japan-specific) keyboard layout.
- ``ABNT2`` for the Brazilian ABNT2 keyboard layout, which is like the ISO
  layout but has 12 keys between the shift keys (the ISO layout has 11).

Description
~~~~~~~~~~~
This is simply a brief, human-readable name of the region (e.g.,
``Canada (French keyboard)``. It is used only in documentation.

Notes
~~~~~
This optional field may contain any notes necessary to describe the
region and any rationale for its settings. It is used only in documentation.

.. _regions-testing:

Testing region settings
~~~~~~~~~~~~~~~~~~~~~~~
When adding a new region, you should test your chosen values to make
sure that the values are valid, and the user experience in OOBE is as
you expect.

First, you should run unit tests making sure that your region settings
are valid. To test values in the public repo, use
``py/test/l10n/regions_unittest.py``. To test values in a private or board
overlay, use :samp:`make overlay-{board} &&
overlay-{board}/py/test/l10n/regions_unittest.py`, where :samp:`{board}` is
either the name of your board or the string ``private``.

To check the OOBE user experience, you can use the
``py/experimental/oobe/region/run_region_oobe.py`` script. This script ssh'es
into a CrOS device, sets its VPD fields according to a region specified on the
command line, and runs the OOBE flow. The device should be running a test
image, and the factory toolkit should not be enabled.

Note that region configurations from your local client are used.

For example, to ssh into a device called ``crosdev`` and test a new
region named ``xx`` that you have added to the public overlay::

  cd ~/trunk/src/platform/factory
  py/experimental/oobe/region/run_region_oobe.py crosdev xx

Or if the region is in the private overlay::

  cd ~/trunk/src/platform/factory
  make overlay-private
  overlay-private/py/experimental/oobe/region/run_region_oobe.py crosdev xx

How regions are set in the factory flow
---------------------------------------
In general, the test list should contain an invocation of the
``shopfloor_service`` test with the ``GetDeviceInfo`` method to
obtain the device-specific data, including region code in VPD.
For instance::

    {
      "pytest_name": "shopfloor_service",
      "args": {
        "method": "GetDeviceInfo"
      }
    }

The returned data from remote Shopfloor Service should return a dictionary to be
stored in factory state data shelve (DeviceData) with region for VPD as::

    {'ro.vpd.region': 'us'}

The ``write_device_data_to_vpd`` test can then be used to read the
``ro.vpd.region`` entry from the device data dictionary and provision into
firmware VPD RO region.

For example::

    {
      "pytest_name": "write_device_data_to_vpd"
    }

Region API
----------

.. py:module:: cros.factory.test.l10n.regions

.. autoclass:: Region
   :members:

The :py:func:`cros.factory.test.l10n.regions.BuildRegionsDict` method is
used to obtain a list of all confirmed regions.  In general, code
should not invoke this directly but rather use
:py:data:`cros.factory.test.l10n.regions.REGIONS`.

.. autofunction:: BuildRegionsDict

.. autodata: REGIONS

.. _where-regions-are-defined:

Where regions are defined
~~~~~~~~~~~~~~~~~~~~~~~~~

The complete set of confirmed regions (regions available for use in
shipping products) is specified by
:py:data:`cros.factory.test.l10n.regions.REGIONS_LIST`.

In addition, there is a module-level attributes used to accumulate
region configuration settings that are thought to be correct but have
not been completely verified yet:
:py:data:`cros.factory.test.l10n.regions.REGIONS_LIST`.

If you cannot add a region to the public factory repository, you may
add it to the private repository that overrides the REGION_LIST.

There is a reference list of "private" regions, shared by private board
overlays, in the ``chromeos-partner-overlay`` repository.

.. rubric:: Footnotes

.. [#l10n] "l10n" is a common abbreviation for "localization": "l",
   plus 10 letters "ocalizatio", plus "n".)
