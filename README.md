# borgBackupTimer
borgBackupTimer (bbtimer) is a simple Python3 timer to run borg backup from a laptop with changing environments.

All this timer is supposed to do is to make sure, whenever your laptop has access to the backup server and circumstances are right, that your borg backup(s) is/are run frequently.

bbtimer uses PyQt5 to display a tray icon that shows the overall status of your backups.
Additionally a right-click menu is provided to
 
 * execute a "_borg list_" on any configured repository
 * run a specific borg backup now
 * open a console with _BORG\_*_ environment variables already set up, so that you can easily manage your repositories
 * exit bbtimer

## Backups
borg backups can be restricted to only run in certain "_environments_"

An environment is nothing but a set of rules/requirements that need to be
satisfied in order for this environment to be "_valid_".
This way it is possible to run borg only in known places, e.g. at your home
and office.

This rules can include
 * local/public ip address
 * current SSID
 * whether the device is connected to the internet by wifi or ethernet
 * whether certain devices are reachable by ping

If a borg backup is "_run_", this means
 * bbtimer checks if there is connectivity to the backup server
 * If there is, bbtimer runs a "_borg create_"
 * If this was successful, bbtimer runs a "_borg prune_"

## Configuration
Configuration is done via a single INI config file. See provided example file ___config.ini___ for more details

## Portability
__A fair warning__: To make this work on your linux machine, you might need to use a custom version of _funcs.py_.
The current implementation uses the following external tools and commands
 * ___ip addr show___ to get local ip addresses
 * ___http://ip.42.pl/raw___ to get the global ip address
 * ___nmcli___ to get the SSID of the wifi network the device is currently connected to (This of course assumes you use NetworkManager)
 * ___ping___ to check connectivity to the backup server and other devices
