#!/usr/bin/env python3
#
# Copyright (c) Facebook, Inc. and its affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

import argparse
import datetime
import math
import time
import sys
import os

def h(x):
    """Translates a number of bytes to a human-readable string."""
    order = 0
    suffix = ['', 'k', 'M', 'G', 'T']
    max_order = len(suffix) - 1
    while abs(x) > 1024 and order < max_order:
        x /= 1024.0
        order += 1
    return '%.2f%s' % (x, suffix[order])


def log(string):
    """Logs timestamped information to stdout."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(ts + ' ' + string)


class Cgroup(object):
    def __init__(self, path, limit_min, limit_max):
        self.path = path
        self.limit = None
        self.limit_min = limit_min
        self.limit_max = limit_max
        self.pressure()  # Ensure psi is available in Linux 4.20+
        self.set_limit(None)

    # Parsing the memory pressure file format:
    #
    # some avg10=0.00 avg60=0.00 avg300=0.00 total=0
    # full avg10=0.00 avg60=0.00 avg300=0.00 total=0

    def pressure(self):
        return float(self.readlines("memory.pressure")[0].split()[1].split('=')[1])

    def total(self):
        return int(self.readlines("memory.pressure")[0].split()[4].split('=')[1])

    # Pressure adjustments

    def scale_limit(self, factor):
        x = self.read_limit()
        x = int(x + x * factor)
        self.set_limit(x)

    def set_limit(self, limit):
        self.import_limit(limit)
        self.write("memory.high", str(self.limit))

    def import_limit(self, limit):
        """Sanitize limit parameter and store it in self.limit."""
        # Init or race condition? Reset limit to memory.current
        if self.read_limit() != self.limit:
            log('Resetting limit to memory.current.')
            limit = self.read_current()
        limit = max(self.limit_min, min(self.limit_max, limit))
        limit &= ~4095
        self.limit = limit

    # Cgroupfs IO

    def read_current(self):
        return int(self.read("memory.current"))

    def read_limit(self):
        x = self.read("memory.high")
        if x == "max\n":
            return (1 << 64) - 1
        return int(x)

    def read(self, filename):
        with open(os.path.join(self.path, filename)) as f:
            return f.read()

    def readlines(self, filename):
        with open(os.path.join(self.path, filename)) as f:
            return f.readlines()

    def write(self, filename, string):
        with open(os.path.join(self.path, filename), 'w') as f:
            f.write(string)


class Senpai(object):
    def __init__(self, conf):
        self.conf = conf
        log('Configuration:')
        for key, val in vars(conf).items():
            log(f'  {key} = {val}')

        self.cgroup = Cgroup(self.conf.cgpath,
                             self.conf.min_size,
                             self.conf.max_size)

        self.last_total = self.cgroup.total()
        self.integral = 0
        self.grace_ticks = self.conf.interval

    def run(self):
        while True:
            time.sleep(1)
            self.tick()

    def tick(self):
        total = self.cgroup.total()
        delta = total - self.last_total
        self.last_total = total
        self.integral += delta
        log('limit=%s pressure=%f time_to_probe=%2d total=%d delta=%d integral=%d' %
            (h(self.cgroup.read_limit()), self.cgroup.pressure(),
             self.grace_ticks, total, delta, self.integral))
        if self.integral > self.conf.pressure:
            # Back off exponentially as we deviate from the target
            # pressure. The backoff coefficient defines how sensitive
            # we are to fluctuations around the target pressure: when
            # the coefficient is 10, the curve reaches the adjustment
            # limit when pressure is ten times the target pressure.
            err = self.integral / self.conf.pressure
            adj = (err / self.conf.coeff_backoff) ** 2
            adj = min(adj * self.conf.max_backoff, self.conf.max_backoff)
            self.adjust(adj)
            self.grace_ticks = self.conf.interval - 1
            return
        if self.grace_ticks:
            self.grace_ticks -= 1
            return
        # Tighten the limit. Like when backing off, the adjustment
        # becomes exponentially more aggressive as observed pressure
        # falls below the target pressure and reaches the adjustment
        # limit when pressure is 1/COEFF_PROBE of target pressure.
        err = self.conf.pressure / max(self.integral, 1)
        adj = (err / self.conf.coeff_probe) ** 2
        adj = min(adj * self.conf.max_probe, self.conf.max_probe)
        self.adjust(-adj)
        self.grace_ticks = self.conf.interval - 1

    def adjust(self, factor):
        log(f'  adjust: {factor}')
        self.cgroup.scale_limit(factor)
        self.integral = 0


parser = argparse.ArgumentParser(description="""
Senpai takes a cgroup and dynamically adjusts its memory range
between MIN_SIZE and MAX_SIZE using psi memory pressure data.

Senpai targets cumulative memory delays of PRESSURE microseconds over
the sampling period of INTERVAL seconds. If observed pressure exceeds
this target, senpai will losen the limit, otherwise tighten it.

Corrective action scales exponentially with the error between observed
pressure and target pressure, and is bounded by MAX_PROBE, MAX_BACKOFF.
These maximums are reached when observed pressure is at 1/COEFF_PROBE
of target pressure, or COEFF_BACKOFF times target pressure, respectively.
""",

formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument('cgpath', type=str)
parser.add_argument('--min-size', type=int, default=100 << 20)
parser.add_argument('--max-size', type=int, default=100 << 30)
parser.add_argument('--interval', type=int, default=6)
parser.add_argument('--pressure', type=int, default=10*1000)
parser.add_argument('--max-probe', type=float, default=0.01)
parser.add_argument('--max-backoff', type=float, default=1.0)
parser.add_argument('--coeff-probe', type=int, default=10)
parser.add_argument('--coeff-backoff', type=int, default=20)

conf = parser.parse_args()
senpai = Senpai(conf)
senpai.run()
