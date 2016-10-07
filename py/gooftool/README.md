Google Factory Tool (gooftool)
==============================

*Google Factory Tool* (`gooftool`), is a standalone program to provide and
support all Google required Chrome OS specific manufacturing flow, including:

 - Enable and check write protection.
 - Leave and check developer mode.
 - Wipe manufacturing data.
 - Verify hardware configuration and setup right Hardware ID (HWID).
 - Ensure ChromeOS image version, channel, and digital signing keys.
 - Sanity check Vital Product Data (VPD).

Since it is very specific to ChromeOS, `gooftool` may need to run on a pure test
image without standard Chrome OS factory software environment and should not
allow arbitrary modification. It is carefully designed that

 - `gooftool` should not use Factory Test or Device API.
 - `gooftool` may only import HWID, test environment and schema (rules), or
   shared utilities (`cros.factory.utils`).

For devices running station mode, `gooftool` is executed as PAR on DUT directly
instead of using Device API.
