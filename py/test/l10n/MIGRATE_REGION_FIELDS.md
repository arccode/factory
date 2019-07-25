Since [crrev.com/c/356873](https://crrev.com/c/356873), we stopped using fixed
numeric id to encode region fields.  Some discussions can be found on
[crbug.com/624257](https://crbug.com/624257).

Basically, instead of

```
region_field: !region_field
...
region_component: !region_component
...
rules:
 - name: verify.regions
  evaluate: >
      Assert(GetVPDValue('ro', 'region') in [
          'us', 'gb',
          ])
```

you should use

```
region_field: !region_field [us, gb]
...
region_component: !region_component
```

in your HWID database.  And this is the default setup for all new HWID
databases.  For HWID database of old projects, if you need to enable a new
region, which is not in the LEGACY_REGIONS_LIST defined by `regions.py`.
Instead of adding the new region to the list, you should migrate to new region
field instead.

You need to do the following:

1. Create a new image id and new image pattern in HWID database.
2. The new image pattern can have everything copied from latest image pattern,
   and then you change `region_field` to `new_region_field`.  You should still
   preserve 8 bits for the new field.
3. In `encoded_fields` section, define `new_region_field` as following:
   ```
   new_region_field: !region_field ['us', 'ca.fr' ...]
   # You should only list countries approved for list device, including the new
   # region you plan to add.
   ```
4. Get approval of new HWID database from device PM and SIE.
