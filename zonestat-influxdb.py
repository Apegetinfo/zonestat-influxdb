#!/usr/bin/python
# -*- coding: utf-8 -*-
'''

Solaris 11 zones monitoring

Run this script from crontab with "-d" to store values in influxdb
Use Grafana to show graphs

2018 <ait.meijin@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import types
import sys
import argparse
import json
import subprocess
from socket import gethostname
import requests

INFX_URL = 'http://influxdb-local:8086'
INFX_DB = 'zonestatdb'


def err_stop(msg):
    if msg:
        print msg
    exit(1)


def gather_stat():

    try:
        data = subprocess.check_output(
            ["/usr/bin/zonestat", "-p", "-r", "psets,memory", "1", "1"],
            stderr=subprocess.STDOUT,
            shell=None,
            universal_newlines=None
        )
        parsed = read_stat(data)
        return parsed

    except subprocess.CalledProcessError as e:
        err_stop("zonestat command failed: {}\nCommand line: [{}]\n\n{}".format(e.returncode, e.cmd, e.output))
    except OSError as e:
        err_stop("Command not found. This script is for Solaris 11 OS only.")
    except:
        err_stop("Unexpected error: {}".format(sys.exc_info()[0]))


def get_parts(line):

    if line:
        parts = line.split(":")
        if parts[1] not in ("header", "footer"):
            return [i.strip("[]") for i in parts]


def parse_line_get_zname(line):

    skip = ("total", "system", "global")

    parts = get_parts(line)
    if not parts:
        return
    if parts[1] == "processor-set":
        # processor-set fields can vary, skip them
        return
    zname = parts[3]
    if zname in skip:
        return

    return zname


def parse_line_get_metric(line, zname):

    try:
        memory_metrics = ("physical-memory", "virtual-memory", "locked-memory")
        cpu_metrics = ("processor-set",)

        parts = get_parts(line)
        if not parts:
            return

        curr_metric = parts[1]

        # get host physical memory
        if (zname == parts[3] and zname == "resource" and curr_metric == "physical-memory"):
            return {curr_metric: parts[4].strip("K")}

        # get zone metrics
        if (zname in parts and zname != "resource"):
            for item in memory_metrics + cpu_metrics:
                if len(parts) < 6:
                    continue
                if curr_metric in memory_metrics:
                    return {curr_metric: {"used": parts[4].strip("K"), "capped": parts[6].strip("K")}}
                if curr_metric in cpu_metrics:
                    if parts[5] == zname:
                        # check if we have `dedicated-cpu` variant of output
                        return {curr_metric: {"used": parts[6], "pused" :parts[7]}}
                    return {curr_metric: {"used": parts[5], "pused": parts[6]}}
    except IndexError:
        err_stop("IndexError in parse_line_get_metric()")


def read_stat(data):

    try:
        lines = data.splitlines()

        znames = filter(lambda(item): item, set(map(parse_line_get_zname, lines)))

        zstat = {}
        for zname in znames:
            zstat[zname] = {}

        for zname in znames:
            for line in lines:
                value = parse_line_get_metric(line, zname)
                if value:
                    zstat[zname].update(value)
        return zstat

    except IndexError:
        err_stop("IndexError in read_stat()")


def to_int(value):

    try:
        n = int(value)
    except ValueError:
        return 0
    return n


def str_units(value, units="K"):

    value = to_int(value)

    if units == "M":
        string = str(value/1024) + "M"
    elif units == "G":
        string = str(value/1024/1024) + "G"
    else:
        string = str(value)
    return string


def get_total(zones, metric, submetric, units="K"):

    total = 0

    for zname in zones:
        if zname == "resource":
            continue
        stat = zones[zname]

        if metric in stat:
            total += to_int(stat[metric][submetric])
        else:
            total = 0
    return str_units(total, units)


def show_totals(zones=None):

    if not zones:
        zones = gather_stat()

    hostmem = str_units(zones["resource"]["physical-memory"], "G")
    zcount = len(zones) - 1

    print "\nZones summary on [{}]:".format(gethostname())
    print "---------------------------------------"
    print "Zones running:\t\t\t {}".format(zcount)
    print "Host memory:\t\t\t{}".format(hostmem)
    print "Total phys memory capped:\t {}".format(get_total(zones, "physical-memory", "capped", "G"))
    print "Total phys memory used:\t\t {}".format(get_total(zones, "physical-memory", "used", "G"))
    print "Total virtual memory used:\t {}".format(get_total(zones, "virtual-memory", "used", "G"))
    print "Total phys memory locked:\t {}".format(get_total(zones, "locked-memory", "used", "G"))


def show_zones(order="mem"):

    descr = {"mem": "virtual memory used", "cpu": "CPU percentage"}

    zstat = gather_stat()
    zones_sorted = []

    if order == "cpu":
        zones_sorted = sort_zones_cpu(zstat)
    else:
        zones_sorted = sort_zones_mem(zstat)

    print "Zones on host [{}]:".format(gethostname())
    print "sorted by {}".format(descr[order])
    print "---------------------------------------"
    for string in zones_sorted:
        print string
    show_totals(zstat)
    return


def sort_zones_mem(zstat):

    zones = {}
    zones_sorted = []

    for zname in zstat.keys():
        if not isinstance(zstat[zname], types.DictType):
            continue
        if "virtual-memory" in zstat[zname]:
            value = zstat[zname]["virtual-memory"]["used"]
            zones[zname] = int(value)

    if zones:
        for key, value in sorted(zones.items(), key=lambda(k, v): (v, k), reverse=True):
            zones_sorted.append("{}:\t{:.1f}GB".format(key, value / 1024 / 1024.0))
        return zones_sorted


def sort_zones_cpu(zstat):

    zones = {}
    zones_sorted = []

    for zname in zstat.keys():
        if not isinstance(zstat[zname], types.DictType):
            continue

        if "processor-set" in zstat[zname]:
            value = zstat[zname]["processor-set"]["pused"]
            zones[zname] = float(value.strip("%"))

    if zones:
        for key, value in sorted(zones.items(), key=lambda(k, v): (v, k), reverse=True):
            zones_sorted.append("{}:\t{}%".format(key, value))
        return zones_sorted


def http_do(method, url, data=None):

    timeout = 5
    req = None

    try:
        if method == "GET":
            print url
            if data:
                req = requests.get(url, params=data, timeout=timeout)
            else:
                req = requests.get(url)
        elif method == "POST":
            headers = {"Content-Type" : "application/octet-stream"}
            req = requests.post(url, data=data, headers=headers, timeout=timeout)
        else:
            err_stop("Unknown HTTP method for http_do()")

        if req:
            if (req.status_code == 204 or req.status_code == 200):
                if method == "GET":
                    print "HTTP {} {}".format(method, req.status_code)
                return req
            else:
                err_stop("HTTP error: {}".format(req.status_code))
        else:
            err_stop("Check connection settings. HTTP code: [{}]".format(req.status_code))

    except requests.ConnectionError:
        err_stop("requests lib: connection error. Check your url and port configuration")
    except requests.HTTPError as e:
        err_stop("requests lib: HTTP error" + e.response.status_code)
    except requests.exceptions.InvalidURL:
        err_stop("requests lib error: bad URL")


def influx_read(what):

    baseurl = INFX_URL.strip("/")

    if what == "db":
        url = "{}/query".format(baseurl)
        data = {"q": "SHOW DATABASES"}
        resp = http_do("GET", url, data)
        return resp.json()

    elif what == "ping":
        url = "{}/ping".format(baseurl)
        resp = http_do("GET", url)
        if resp.status_code == 204:
            print "OK"
        return
    else:
        return None


def influx_write(data):

    baseurl = INFX_URL.strip("/")
    url = "{}/write?db={}".format(baseurl, INFX_DB)
    resp = http_do("POST", url, data)
    return


# debug def
def show_dbs():

    text = influx_read("db")
    if text:
        print json.dumps(text, indent=4)



def get_all_totals(zstat):
    # gather totals for all metrics
    totals = {}

    mem_metrics = ("physical-memory", "virtual-memory", "locked-memory")
    mem_submetrics = ("used", "capped")

    for metric in mem_metrics:
        totals[metric] = {}
        for submetric in mem_submetrics:
            totals[metric].update({submetric : get_total(zstat, metric, submetric)})

    totals["hostmem"] = zstat["resource"]["physical-memory"]
    totals["zcount"] = len(zstat) - 1
    return totals


# format metrics and store them into InfluxDB
def store_metrics():

    host = gethostname()
    zstat = gather_stat()
    totals = get_all_totals(zstat)
    data = ""

    for metric in totals:
        if isinstance(totals[metric], types.DictType):
            for submetric in totals[metric]:
                data += "{},host={},type={} value={}\n".format(metric, host, submetric, totals[metric][submetric])
        else:
            data += "{},host={} value={}\n".format(metric, host, totals[metric])
    # print(data)
    influx_write(data)


def main():

    parser = argparse.ArgumentParser(
        description="Script for collecting Solaris Zones usage statistics.",
        epilog="*Use '-d' when running this script as a cronjob to collect and store metrics."
        )
    parser.add_argument(
        "-z",
        nargs="?",
        choices=[None, "mem", "cpu"],
        default=None,
        help="show zones resource usage - totals (default) or show zone list sorted by 'cpu' or 'mem'"
        )
    parser.add_argument("-d", action="store_true", help="save stats to a database")
    parser.add_argument("-dp", action="store_true", help="test database connection")
    args = parser.parse_args()

    if args.dp:
        influx_read("ping")
    elif args.d:
        store_metrics()
    elif args.z is not None:
        show_zones(args.z)
    else:
        show_totals()


if __name__ == '__main__':
    main()
