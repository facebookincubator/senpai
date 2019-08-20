# Senpai

Senpai is an automated memory sizing tool for container applications.

## Background

Determining the exact amount of memory required by an application (the
*workingset size*) is a difficult, error-prone task.

Libraries and code pages used during startup are loaded into memory
only to be never touched again afterwards. On top of that, the Linux
filesystem cache doesn't kick out cold data until that memory is
required for new data. ***Allocated* memory is not a good proxy for
*required* memory**. This makes it difficult to provision memory
correctly and maintain adequate safety margins: Too little, and the
applications experience thrashing or out-of-memory kills during load
peaks; too much, and costly hardware resources are being wasted.

Senpai is a userspace tool that determines the actual memory
requirement of containerized applications.

Using Linux psi metrics and cgroup2 memory limits, senpai applies just
enough memory pressure on a container to page out the cold and unused
memory pages that aren't necessary for nominal workload
performance. It dynamically adapts to load peaks and troughs, and so
provides a workingset profile of an application over time.

This information helps system operators eliminate waste, shore up for
contingencies, optimize task placement in compute grids, and plan
long-term capacity/hardware requirements.

## Examples

An example kernel compile job has a peak memory consumption of 800M:

    $ time make -j4 -s
    real    3m58.050s
    user    13m33.735s
    sys     1m30.130s

    $ sort -n memory.current-nolimit.log | tail -n 1
    803934208

However, when a memory limit of 600M is applied, the job finishes in
the same amount of time - with 25% less available memory:

    # echo 600M > memory.high

    $ time make -j4 -s
    real    4m0.654s
    user    13m28.493s
    sys     1m31.509s

    $ sort -n memory.current-600M.log | tail -n 1
    629116928

Clearly, the full 800M aren't required. But 600M still has an unknown
amount of slack - even a 400M limit doesn't materially affect runtime:

    # echo 400M > memory.high

    $ time make -j4 -s
    real    4m3.186s
    user    13m20.452s
    sys     1m31.085s

    $ sort -n memory.current-400M.log | tail -n 1
    419368960

At 300M, on the other hand, the workload struggles to make forward
progress and finish within a reasonable amount of time:

    # echo 300M > memory.high

    $ time make -j4 -s
    ^C
    real    9m9.974s
    user    10m59.315s
    sys     1m16.576s

Finding the exact cutoff where job performance begins to plummet is a
tedious trial-and-error process. It also only works when the job does
a fixed amount of work every time it runs, like in this example, but
that isn't true for many datacenter services that run indefinitely and
process highly variable user input.

Senpai determines the memory requirement of an application while the
application is running:

    # senpai .
    2019-08-19 14:26:05 Configuration:
    2019-08-19 14:26:05   cgpath = /sys/fs/cgroup/kernelbuild
    2019-08-19 14:26:05   min_size = 104857600
    2019-08-19 14:26:05   max_size = 107374182400
    2019-08-19 14:26:05   interval = 5
    2019-08-19 14:26:05   pressure = 1000
    2019-08-19 14:26:05   max_probe = 0.01
    2019-08-19 14:26:05   max_backoff = 0.1
    2019-08-19 14:26:05   log_probe = 1000
    2019-08-19 14:26:05   log_backoff = 10
    2019-08-19 14:26:05 Resetting limit to memory.current.
    2019-08-19 14:26:06 limit=100.00M pressure=0.000000 time_to_probe= 6 total=117669927 delta=0 integral=0
    2019-08-19 14:26:07 limit=100.00M pressure=0.000000 time_to_probe= 5 total=117669927 delta=0 integral=0
    2019-08-19 14:26:08 limit=100.00M pressure=0.000000 time_to_probe= 4 total=117669927 delta=0 integral=0

    $ time make -j4 -s

    2019-08-19 14:26:09 limit=100.00M pressure=0.000000 time_to_probe= 3 total=117678359 delta=8432 integral=8432
    2019-08-19 14:26:09   backoff: 0.09259305978684715
    2019-08-19 14:26:10 limit=109.26M pressure=0.180000 time_to_probe= 5 total=117719536 delta=41177 integral=41177
    2019-08-19 14:26:10   backoff: 0.1
    2019-08-19 14:26:11 limit=120.18M pressure=0.180000 time_to_probe= 5 total=117768197 delta=48661 integral=48661

    ...

    2019-08-19 14:26:43 limit=340.48M pressure=0.160000 time_to_probe= 5 total=118045638 delta=202 integral=202
    2019-08-19 14:26:44 limit=340.48M pressure=0.130000 time_to_probe= 4 total=118045638 delta=0 integral=202
    2019-08-19 14:26:45 limit=340.48M pressure=0.130000 time_to_probe= 3 total=118045638 delta=0 integral=202
    2019-08-19 14:26:46 limit=340.48M pressure=0.110000 time_to_probe= 2 total=118045638 delta=0 integral=202
    2019-08-19 14:26:47 limit=340.48M pressure=0.110000 time_to_probe= 1 total=118045690 delta=52 integral=254
    2019-08-19 14:26:48 limit=340.48M pressure=0.090000 time_to_probe= 0 total=118045690 delta=0 integral=254
    2019-08-19 14:26:48   probe: -0.001983887611266873
    2019-08-19 14:26:49 limit=339.80M pressure=0.090000 time_to_probe= 5 total=118045690 delta=0 integral=0

    ...

    real    4m9.420s
    user    13m21.723s
    sys     1m33.037s

    $ sort -n memory.current-senpai.log | tail -n 1
    347762688

## Requirements
* Linux v4.20 or up with CONFIG_PSI=y
* python3

## License
senpai is GPL v2.0 licensed, as found in the LICENSE file.
