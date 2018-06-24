# zonestat-influxdb
Solaris 11 Zones monitoring script with influxdb as a backend.

Usage:
* To view current metrics run the script without arguments.
* [-z] view zones metrics in human-readable format.
* [-z mem|cpu] show list of zones sorted by virtual memory or cpu usage.
* [-d] gather and store metrics. **Note: edit influxdb address and database name in the script and run it periodically (as a cronjob).**


