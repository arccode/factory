CrOS Factor Init: Main
======================
This folder supports running programs when the *factory* service on a
ChromiumOS factory test image starts. To add your own program, create a
`NAME.sh` in `main.d` folder.

If the `NAME.sh` has `+x` file mode set, it's default enabled; otherwise it is
default disabled (and will be executed by sh).

To explicitly enable or disable a service, touch and create a tag file
 `enable-NAME` or `disable-NAME`.

For example:

    -rwxr-xr-x goofy.sh
    -rw-r--r-- whale_servo.sh

By default the system will only invoke `goofy.sh`.

To disable running goofy, create a `disable-goofy` file.
To enable running whale_servo, create a `enable-whale_servo` file.
