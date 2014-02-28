# -*- coding: utf-8 -*-
"""
    scap.utils
    ~~~~~~~~~~
    Contains misc utility functions.

"""
import contextlib
import errno
import fcntl
import imp
import json
import os
import random
import re
import socket
import struct


def read_dsh_hosts_file(path):
    """Reads hosts from a file into a list.

    Blank lines and comments are ignored.
    """
    try:
        with open(os.path.join('/etc/dsh/group', path)) as hosts_file:
            return re.findall(r'^[\w\.]+', hosts_file.read(), re.MULTILINE)
    except IOError, e:
        raise IOError(e.errno, e.strerror, path)


def get_config(cfg_file='/usr/local/lib/mw-deployment-vars.sh'):
    """Load environment variables from mw-deployment-vars.sh."""
    try:
        dep_env = imp.load_source('__env', cfg_file)
    except IOError, e:
        raise IOError(e.errno, e.strerror, cfg_file)
    else:
        return {k: v for k, v in dep_env.__dict__.items()
                if k.startswith('MW_')}


def wikiversions(location):
    """Get a collection of active MediaWiki versions.

    :param location: Directory to read wikiversions.json from
    :returns: dict of {version:wikidb} values
    """
    with open(os.path.join(location, 'wikiversions.json')) as f:
        wikiversions = json.load(f)

    versions = {}
    for wikidb, version in wikiversions.items():
        version = version[4:]
        if version not in versions:
            versions[version] = wikidb

    return versions


@contextlib.contextmanager
def lock(filename):
    """Context manager. Acquires a file lock on entry, releases on exit."""
    with open(filename, 'w+') as lock_fd:
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)


def human_duration(elapsed):
    """Format an elapsed seconds count as human readable duration.

    >>> human_duration(1)
    '00m 01s'
    >>> human_duration(65)
    '01m 05s'
    >>> human_duration(60*30+11)
    '30m 11s'
    """
    return '%02dm %02ds' % divmod(elapsed, 60)


def find_nearest_host(hosts, port=22, timeout=1):
    """Given a collection of hosts, find the one that is the fewest
    number of hops away.

    >>> # Begin test fixture
    >>> import socket
    >>> fixture_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    >>> fixture_socket.bind(('127.0.0.1', 0))
    >>> fixture_socket.listen(1)
    >>> fixture_port = fixture_socket.getsockname()[1]
    >>> # End test fixture
    >>> find_nearest_host(['127.0.0.1'], port=fixture_port)
    '127.0.0.1'

    :param hosts: Hosts to check
    :param port: Port to try to connect on (default: 22)
    :param timeout: Timeout in seconds (default: 1)
    """
    host_map = {}
    for host in hosts:
        try:
            host_map[host] = socket.getaddrinfo(host, port)[0]
        except socket.gaierror:
            continue

    for ttl in range(1, 30):
        if not host_map:
            break
        for host, info in random.sample(host_map.items(), len(host_map)):
            family, type, proto, _, addr = info
            s = socket.socket(family, type, proto)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL,
                         struct.pack('I', ttl))
            s.settimeout(timeout)
            try:
                s.connect(addr)
            except socket.error as e:
                if e.errno != errno.EHOSTUNREACH:
                    del host_map[host]
                continue
            except socket.timeout:
                continue
            else:
                return host
            finally:
                s.close()