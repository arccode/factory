CrOS Factory: Init system
=========================
The init folder contains configurations to change ChromeOS boot flow into
factory-ready environment.

The goal is to start UI (Chrome) in Kiosk mode, and browsing factory web UI
port on default. And the real flow is:

0. This folder should be copied into `/mnt/stateful_partition` as path
   `dev_image/factory/init`, and mounted at `/usr/local/factory/init`.

1. `/etc/init/factory-init.conf` must be executed when *starting*
   `boot-services.conf` (before UI is started), then calls
   `factory/init/startup`.

2. `factory/init/startup` will apply any rules in in its sub folders, for
   example binding a customized `/etc/chrome_dev.conf` (which will be parsed
   by Chrome session manager and applied for startup in `ui.conf`).

3. when `factory.conf` starts, it will invoke `factory/init/startup main`
   which loads rules from `main.d`. By default this should start Goofy UI, but
   it may also be customized to start other services like Whale.

Now, when everything is set, we will have a new and unified boot flow:

    (upstart) startup -> [chromeos_startup] -> (upstart) boot_services ->
    (upstart) factory-init -> [factory/init/startup init] ->
    (upstart) factory -> [factory/init/startup main] -> [goofy_control start] ->
    (upstart) ui (Chrome) -> [goofy] ->
    [emit login-prompt-visible] -> (upstart) other system services ...

And when developers run factory_restart, it brings up these services in same
flow (first factory then chrome).

See `main.d/README.md` for more information of how to add (also enable or
disable) new rules into each stage.

 - `common.d`: Rules applied on all systems in system init.
 - `iptables.d`: Rules applied for network setup.
 - `goofy.d`: Rules applied according to factory configuration (run presenter,
     device, or monolithic mode).
 - `main.d`: Rules applied for factory main service (`factory.conf`).
