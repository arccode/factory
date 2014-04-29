Branding
========

.. note::

  The following information applies only to M35 and up.  Before M35,
  the RLZ brand code is read from ``/opt/oem/etc/BRAND_CODE`` in the
  release rootfs, not the VPD; and ``customization_id`` is not
  supported at all.  In M35 and up, ``/opt/oem/etc/BRAND_CODE`` is
  also supported for backward compatibility, but it is recommended to
  set the VPD value instead.

Chromium OS relies on two fields in the RO VPD, ``rlz_brand_code`` and
``customization_id``, to provide branding customization and revenue
tracking.  An RLZ brand code must be set for every device (``gooftool
verify`` checks for this), but a customization ID is optional.

``rlz_brand_code`` is a four-letter string like ``ZZCR``.
``customization_id`` is a series of letters and digits, optionally
followed by a hyphen and another series of letters and digits, like
``FOO1`` or ``FOO1-BAR``.  The particular values for these fields
are assigned by the partner engineering team.

These values may be set in the factory flow in various ways.  You may set the
``rlz_brand_code`` and ``customization_id`` properties in the ``TestListArgs``
structure to:

- ``None``, to not set any value at all.
- A fixed string.  ``'ZZCR'`` may be used for testing ``rlz_brand_code``.
- ``FROM_DEVICE_DATA``, to use the value obtained from the device data
  dictionary (from the shop floor server).  This is useful if a single
  image will be used to support multiple brand codes and/or
  customizations.

These arguments are passed directly to the ``vpd`` test, which is
responsible for setting the VPD fields accordingly.

Most projects will likely want a fixed brand code and no customization_id::

  class TestListArgs(object):
    ...
    rlz_brand_code = 'ZZCR'  # ZZCR is for testing only!
    customization_id = None  # No variant customization

Projects that have variant ``rlz_brand_code`` and/or
``customization_id`` values for the same image will likely want to get
both from the shop floor server::

  class TestListArgs(object):
    ...
    rlz_brand_code = FROM_DEVICE_DATA
    customization_id = FROM_DEVICE_DATA

Note that the ``gooftool verify`` command checks for the presence of a
brand code either in the ``rlz_brand_code`` RO VPD, or in the
``/opt/oem/etc/BRAND_CODE`` file in rootfs; one of these must be set
in order for the device to finalize. ``customization_id`` is optional
and need not be set anywhere.
