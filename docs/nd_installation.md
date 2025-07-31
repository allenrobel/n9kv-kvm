# Install Nexus Dashboard

Now that the servers we need are setup and running, let's install
Nexus Dashboard.

## Things to be aware of

Before beginning, ND will ask you to connect with a web browser after
the initial CLI install is complete.  If you use a proxy server, make
sure that you configure your browser NOT to use the proxy server
for the ND address.  E.g. configure the `NO_PROXY` environment variable
(some apps may read this as lowercase, so best to configure both).

If you already have `NO_PROXY` configured, add 192.168.11.2 to your existing definition.

```bash
export NO_PROXY=192.168.11.2
export no_proxy=192.168.11.2
```

If you use Google Chrome, you can invoke it to not use a proxy (typically for
debugging when things aren't working as expected.)

```bash
google-chrome --no-proxy-server &
```

With that out of the way, let's get started.

## CLI based initial bringup

Follow the link below for initial CLI phase of the Nexus Dashboard bringup.

[ND Bringup - CLI Phase](./nd_bringup_cli.md)

## ND 4.1 Browser based final bringup

Follow the link below for the final phase of the Nexus Dashboard 4.1 bringup.

[ND 4.1 Configuration Web Browser](./nd4_bringup_web.md)

## ND 3.2 Browser based final bringup

Follow the link below for the final phase of the Nexus Dashboard 3.2 bringup.

[ND 3.2 Configuration Web Browser](./nd3_bringup_web.md)
