# zonestat-influxdb
Solaris 11 Zones monitoring script with influxdb as a backend.

Usage:
* To gather and store metrics: modify influxdb address in the script (and database name if you need to) and run it from cron with a "-d" argument.
* To see current metrics run the script without arguments.

