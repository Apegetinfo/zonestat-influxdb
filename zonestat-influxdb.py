#!/usr/bin/python
#
# Solaris 11 zones monitoring
#
#
# Run this script from crontab with "-d" to store values in influxdb
# Use Grafana to show graphs
#
# 2018 <ait.meijin@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.



import time
import sys
import json
import subprocess
import requests
import types
from socket import gethostname


INFX_URL = 'http://influxdb.local:8086/'
INFX_DB = 'zonestatdb'



def show_help():
    # you shall not...
    pass



def err_stop(msg):
    if msg:
        print msg
    sys.exit(1)


def gatherstat():

    try:
        input = subprocess.check_output(["/usr/bin/zonestat", "-p", "-r", "memory", "1", "1"], stderr = subprocess.STDOUT, shell=None, universal_newlines=None)
        return readstat(input)

    except subprocess.CalledProcessError as e:
        err_stop("zonestat command failed: {}\nCommand line: [{}]\n\n{}".format( e.returncode, e.cmd, e.output))
    except OSError as e:
        err_stop("Command not found. This script is for Solaris 11 OS only.")
    except:
        print "Unexpected error:", sys.exc_info()[0]
    sys.exit(1)


def readstat(input):

    zones = {}
    lines = input.splitlines()
    skip = ("total", "system", "global")

    try:
        for line in lines:

            if (len(line) > 0):

                parts = line.split(":")

                if (parts[1] in ("header", "footer")):
                    continue

            else:
                continue

            zname = parts[3].strip("[]")

            if (zname in skip):
                continue

            value = parts[4].replace("K","")

            if (zname == "resource"):
                zones["hostmem"] = value
                continue

            if (parts[1] == "physical-memory"):
                zones[zname] = ({"pmem" : value, "capped" : parts[6].replace("K","")})

            elif (parts[1] == "virtual-memory"):
                zones[zname].update({"vmem" : value})

            elif (parts[1] == "locked-memory"):
                zones[zname].update({"locked" : value})

            else:
                continue
    except IndexError:
            print "Debug: index error in readstat()."
            sys.exit(1)

    return zones


def to_int(x):

    try:
        n = int(x)
    except ValueError:
        return 0
    return n


def str_units(value, units="K"):

    if units is "M":
        s = str(value/1024) + "M"
    elif units is "G":
        s = str(value/1024/1024) + "G"
    else:
        s = str(value)
    return s


def get_total(zones, metric, units="K"):

    total = 0

    if (metric == "zcount"):
        s =  str(len(zones))
        return s

    for zn in zones:

        if (zn == "hostmem"):
            continue

        z = zones[zn]

        if metric in z:
            total += to_int(z[metric])
        else:
            total = 0

    return str_units(total, units)
  


def get_all_totals(zstat):

    totals = {}
    metrics = ("zcount", "capped", "pmem", "vmem", "locked")
    
    for m in metrics:
        totals[m] = get_total(zstat, m)

    totals["hostmem"] = zstat["hostmem"]
    return totals 


def showtotals(z=None):

    if not z:
        z = gatherstat()
    
    print "\nZones summary:"
    print "---------------------------------------"
    print "Host memory:\t\t\t{}".format(str_units(int(z["hostmem"]), "G"))
    print "Zones running:\t\t\t {}".format(get_total(z, "zcount"))
    print "Total phys memory capped:\t {}".format(get_total(z, "capped", "G"))
    print "Total phys memory used:\t\t {}".format(get_total(z, "pmem", "G"))
    print "Total virtual memory used:\t {}".format(get_total(z, "vmem", "G"))
    print "Total phys memory locked:\t {}".format(get_total(z, "locked", "G"))
    

def show_zones():

    zstat = gatherstat()
    zmemstat = {}

    for zname in zstat.keys():

        if not isinstance(zstat[zname], types.DictType):
            continue

        pmem = zstat[zname]["pmem"]
        zmemstat[zname] = int(pmem)
    

    print "Zones on host {}:".format(gethostname())
    print "---------------------------------------"
    for key, value in sorted(zmemstat.items(), key=lambda(k,v): (v,k)):
        print "{}:\t{:.1f}GB".format(key, value / 1024 / 1024.0)
    
    showtotals(zstat)
    return



def http_do(method, url, data):

    r = None

    try:
        if (method == "GET"):
            r = requests.get(url, params=data)

        elif (method == "POST"):
            headers = {"Content-Type" : "application/octet-stream"}
            r = requests.post(url, data=data, headers=headers)
        else:
            err_stop("Unknown HTTP method")

        if r:
            print r.url
            print "HTTP {} {}".format(method, r.status_code)

            if (r.status_code == 204 or r.status_code == 200):
                return r
            else:
                err_stop("HTTP error: {}".format(r.status_code))
        else:
            err_stop("No response from requests lib")

    except requests.ConnectionError:
        err_stop("requests lib: connection error")
    except requests.HTTPError as e:
        err_stop("requests lib: HTTP error" + e.response.status_code)
    except requests.exceptions.InvalidURL:
        err_stop("requests lib error: bad URL")


def influx_read(what):

    global INFX_URL

    url = INFX_URL + "query"

    if (what == "db"):
        data  = {"q":"SHOW DATABASES"}
        resp = http_do("GET", url, data)
        return resp.json()
    else:
        return None


def show_dbs():
    text = influx_read("db")

    if text:
        print json.dumps(text, indent=4)


def influx_write(data):

    global INFX_URL
    global INFX_DB

    url = INFX_URL + "write?db=" + INFX_DB
    resp = http_do("POST", url, data)


def store_metrics():

    zstat = gatherstat()

    data = ""
    totals = get_all_totals(zstat)

    for key,val in totals.items():
        data += "{},host={} value={}\n".format(key, gethostname(), val)

    influx_write(data)


#START

try:
    if sys.argv[1]:
        a = sys.argv[1]

    if (a == "-d"):
        # Save stats to a database
        store_metrics()

    elif (a == "-ds"):
        show_dbs()

    elif (a == "-zs"):
        show_zones()
    else:
        show_help()

    sys.exit(0)

except IndexError:
    pass

# Human readable output by default
showtotals()


