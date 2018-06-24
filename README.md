# zonestat-influxdb
Solaris 11 Zones monitoring script with influxdb as a backend.

Usage:
* To view current metrics run the script without arguments.
* [-z] view zones metrics in human-readable format.
* [-z cpu|mem ] show list of zones sorted by cpu or virtual memory usage.
* [-d] gather and store metrics into influxdb.

 Installation: 
* Edit influxdb server address and database name in the script and run it periodically (as a cronjob).
* Not that zonestat is slow, use cron intervals not less than 3 mins, depending on number of monitored zones.


