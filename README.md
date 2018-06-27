# zonestat-influxdb
Solaris 11 Zones monitoring script with influxdb as a backend.

Usage:
* To view current metrics run the script without arguments.
* [-z] view zones metrics in human-readable format.
* [-z cpu|mem ] show list of zones sorted by cpu or virtual memory usage.
* [-d] gather and store metrics into influxdb.

 Installation: 
* Edit [influxdb](https://www.influxdata.com/) server address and database name in the script and run it periodically (as a cronjob).
* Note that zonestat is slow, use cron intervals not less than 3-5 mins, depending on a number of monitored zones.
* You can use [Grafana](https://grafana.com/) to build graphs and dashboards, using influxdb as a data source. Use provided panel JSON file as example.


