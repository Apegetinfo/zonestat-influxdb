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
        input = subprocess.check_output(['/usr/bin/zonestat', '-p', '-P', 'zones', '-r', 'memory', '1', '1'], stderr = subprocess.STDOUT, shell=None, universal_newlines=None)
        return readstat(input)

    except subprocess.CalledProcessError as e:
        err_stop("zonestat command failed: %s\nCommand line: [%s]\n\n%s" % ( e.returncode, e.cmd, e.output))
    except OSError as e:
        err_stop("Command not found. This script is for Solaris 11 OS only.")
    except:
        print "Unexpected error:", sys.exc_info()[0]
    sys.exit(1)


def readstat(input):

    zones = {}
    lines = input.splitlines()

    for line in lines:

        if (len(line) > 0):

            parts = line.split(':')

            if (len(parts) < 8):
                continue
        else:
            continue

        zname = parts[3]

        if (zname == 'global'):
            continue

        value = parts[4].replace('K','')

        if (parts[1] == 'physical-memory'):
            zones[zname] = ({"pmem" : value, "capped" : parts[6].replace('K','')})

        elif (parts[1] == 'virtual-memory'):
            zones[zname].update({"vmem" : value})

        elif (parts[1] == 'locked-memory'):
            zones[zname].update({"locked" : value})

        else:
            continue

    return zones


def to_int(x):
    try:
        n = int(x)
    except ValueError:
        return 0
    return n

def get_total(zones, metric, units='K', mtype='str'):

    total = 0

    if metric is 'zcount':
        return str(len(zones))

    for zn in zones:
        z = zones[zn]

        if metric in z:
            total += to_int(z[metric])
        else:
            total = 0

    if mtype is 'int':
        return total
    else:
        if units is 'M':
            s = str(total/1024)+"M"
        elif units is 'G':
            s = str(total/1024/1024)+"G"
        else:
            s = str(total)
        return s


def get_all_totals(zstat):

    totals = {}
    metrics = [ 'zcount', 'capped', 'pmem', 'vmem', 'locked' ]
    
    for m in metrics:
         totals[m] = get_total(zstat, m)

    return totals 


def showtotals(z):
    print
    print "Zones summary:"
    print "---------------------------------------"
    print "Zones running:\t\t\t %s" % (get_total(z, 'zcount'))
    print "Total phys memory capped:\t %s " % (get_total(z, 'capped', 'G'))
    print "Total phys memory used:\t\t %s " % (get_total(z, 'pmem', 'G'))
    print "Total virtual memory used:\t %s " % ( get_total(z, 'vmem', 'G'))
    print "Total phys memory locked:\t %s " %  (get_total(z, 'locked', 'G'))


def json_out(z):
    print json.dumps({
        "data": [
                {
                    'pmemused': get_total(z, 'pmem')
                },
                {
                    'pmemcapped': get_total(z, 'capped')
                },
                {
                    'vmemtotal': get_total(z, 'vmem')
                },
                {
                    'pmemlocked': get_total(z, 'locked')
                },
                {
                    'zcount': (get_total(z, 'zcount'))
                }
        ]
    }, indent=4)


def http_do(method, url, data):

    r = None

    try:
        if (method == 'GET'):
            r = requests.get(url, params=data)

        elif (method == 'POST'):
            headers = {'Content-Type' : 'application/octet-stream'}
            r = requests.post(url, data=data, headers=headers)
        else:
            err_stop("Unknown HTTP method")

        if r:
            print r.url
            print "HTTP %s %s" % (method, r.status_code)

            if (r.status_code == 204 or r.status_code == 200):
                return r
            else:
                err_stop("HTTP error: " + str(r.status_code))
        else:
            err_stop("No response from requests lib")

    except requests.ConnectionError:
        err_stop("requests lib Connection error")
    except requests.HTTPError as e:
        err_stop("requests lib HTTP error" + e.response.status_code)
    except requests.exceptions.InvalidURL:
        err_stop("requests lib error: bad URL")


def influx_read(what):

    global INFX_URL

    url = INFX_URL + 'query'

    if (what == 'db'):
        data  = {"q":"SHOW DATABASES"}
        resp = http_do('GET', url, data)
        return resp.json()
    else:
        return


def show_dbs():
    text = influx_read('db')
    print json.dumps(text, indent=4)


def influx_write(data):

    global INFX_URL
    global INFX_DB

    url = INFX_URL + 'write?db='+ INFX_DB
    resp = http_do('POST', url, data)


def store_metrics(zstat):

    data = ""
    host = gethostname()
    print host
    tot = get_all_totals(zstat)

    for key,val in tot.items():
        data += "{},host={} value={}\n".format(key,host,val)

    influx_write(data)



#START

try:
    sys.argv[1]
    a = sys.argv[1]

    if (a == "-z"):
        # stats to JSON
        zstat = gatherstat()
        json_out(zstat)

    elif (a == "-d"):
        # save stats to db
        zstat = gatherstat()
        store_metrics(zstat)

    elif (a == "-ds"):
        show_dbs()

    else:
        show_help()

    sys.exit(0)

except IndexError:
    pass

# Human readable output by default
zstat = gatherstat()
showtotals(zstat)


