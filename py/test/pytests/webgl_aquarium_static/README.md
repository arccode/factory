WebGL Aquarium Test
===================
The files that are required to run the
[WebGL Aquarium](http://webglsamples.org/aquarium/aquarium.html) test will be
fetched from [CPFE](https://www.google.com/chromeos/partner/fe) BCS during
build. If you want to get the files manually, you can just run:

    emerge-<board> factory

and then copy out the files from:

    /build/<board>/usr/local/factory/py/test/pytests/webgl_aquarium_static


### Instructions to build the tarball

The file `webgl-aquarium.tar.bz2` on BCS was created from the sources of:

  https://code.google.com/p/webglsamples/

You have to check out the source code with mecurial. Once you have the source
code, do the following modifications:

  1. cd to the `aquarium/` directory.
  2. Remove `source_asserts/` to reduce size.
  3. Manually copy `khronos/`, `jquery-ui-1.8.2.custom/`, `tdl/` directories
     from the upper-level directory.
  4. Modify `aquarium.html` to point the src of all the script tags to current
     directory instead of upper-level directory.

and finally, switch to the upper-level directory and run:

    tar -jcvf webgl-aquarium-<data tag>.tar.bz2 webgl_aquarium_static/

to generate the tarball and upload to BCS. After you upload the tarball to BCS,
go to:

    https://storage.cloud.google.com/?arg=chromeos-localmirror

switch to `distfiles/`, find the tarball you uploaded, and check "Share
Publicly".
