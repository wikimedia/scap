# -*- coding: utf-8 -*-
"""
| Imported from: `python-pure-cdb <https://python-pure-cdb.googlecode.com/>`_
| Author: David Wilson
| License: MIT

Manipulate DJB's Constant Databases. These are 2 level disk-based hash tables
that efficiently handle many keys, while remaining space-efficient.

    http://cr.yp.to/cdb.html

When generated databases are only used with Python code, consider using hash()
rather than djb_hash() for a tidy speedup.

.. note::
    Minor alterations made to comply with PEP8 style check and to remove
    attempt to import C implementation of djb_hash. -- bd808, 2014-03-04
"""
from __future__ import absolute_import

from itertools import chain
from _struct import Struct


def py_djb_hash(s):
    u"""
    Return the value of DJB's hash function for the given 8-bit string.

    >>> py_djb_hash('')
    5381
    >>> py_djb_hash('\x01')
    177572
    >>> py_djb_hash('€')
    193278953
    """
    h = 5381
    for c in s:
        h = (((h << 5) + h) ^ ord(c)) & 0xffffffff
    return h


# 2014-03-04 bd808: removed try block for importing C hash implementation
DJB_HASH = py_djb_hash

READ_2_LE4 = Struct('<LL').unpack
WRITE_2_LE4 = Struct('<LL').pack


class Reader(object):

    """
    A dictionary-like object for reading a Constant Database.

    Reader accesses through a string or string-like sequence
    such as mmap.mmap().
    """

    def __init__(self, data, hashfn=DJB_HASH):
        """
        Create an instance reading from a sequence and hash keys using hashfn.

        >>> Reader(data='')
        Traceback (most recent call last):
        ...
        IOError: CDB too small
        >>> Reader(data='a' * 2048) #doctest: +ELLIPSIS
        <scap.cdblib.Reader object at 0x...>
        """
        if len(data) < 2048:
            raise IOError('CDB too small')

        self.data = data
        self.hashfn = hashfn

        self.index = [READ_2_LE4(data[i:i + 8]) for i in range(0, 2048, 8)]
        self.table_start = min(p[0] for p in self.index)
        # Assume load load factor is 0.5 like official CDB.
        self.length = sum(p[1] >> 1 for p in self.index)

    def iteritems(self):
        """Like dict.iteritems(). Items are returned in insertion order."""
        pos = 2048
        while pos < self.table_start:
            klen, dlen = READ_2_LE4(self.data[pos:pos + 8])
            pos += 8

            key = self.data[pos:pos + klen]
            pos += klen

            data = self.data[pos:pos + dlen]
            pos += dlen

            yield key, data

    def items(self):
        """Like dict.items()."""
        return list(self.iteritems())

    def iterkeys(self):
        """Like dict.iterkeys()."""
        return (p[0] for p in self.iteritems())
    __iter__ = iterkeys

    def itervalues(self):
        """Like dict.itervalues()."""
        return (p[1] for p in self.iteritems())

    def keys(self):
        """Like dict.keys()."""
        return [p[0] for p in self.iteritems()]

    def values(self):
        """Like dict.values()."""
        return [p[1] for p in self.iteritems()]

    def __getitem__(self, key):
        """Like dict.__getitem__()."""
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def has_key(self, key):
        """Return True if key exists in the database."""
        return self.get(key) is not None
    __contains__ = has_key

    def __len__(self):
        """Return the number of records in the database."""
        return self.length

    def gets(self, key):
        """Yield values for key in insertion order."""
        # Truncate to 32 bits and remove sign.
        h = self.hashfn(key) & 0xffffffff
        start, nslots = self.index[h & 0xff]

        if nslots:
            end = start + (nslots << 3)
            slot_off = start + (((h >> 8) % nslots) << 3)

            for pos in chain(range(slot_off, end, 8),
                             range(start, slot_off, 8)):
                rec_h, rec_pos = READ_2_LE4(self.data[pos:pos + 8])

                if not rec_h:
                    break
                elif rec_h == h:
                    klen, dlen = READ_2_LE4(self.data[rec_pos:rec_pos + 8])
                    rec_pos += 8

                    if self.data[rec_pos:rec_pos + klen] == key:
                        rec_pos += klen
                        yield self.data[rec_pos:rec_pos + dlen]

    def get(self, key, default=None):
        """Get the first value for key, returning default if missing."""
        # Avoid exception catch when handling default case; much faster.
        return next(chain(self.gets(key), (default,)))


class Writer(object):
    """Object for building new Constant Databases, and writing them to a
    seekable file-like object."""

    def __init__(self, fp, hashfn=DJB_HASH):
        """
        Create an instance writing to a file-like object and hash keys.

        It uses hashfn to hash keys.

        >>> import tempfile
        >>> temp_fp = tempfile.TemporaryFile()
        >>> Writer(fp=temp_fp, hashfn=py_djb_hash) #doctest: +ELLIPSIS
        <scap.cdblib.Writer object at 0x...>
        """
        self.fp = fp
        self.hashfn = hashfn

        fp.write('\x00' * 2048)
        self._unordered = [[] for i in range(256)]

    def put(self, key, value=''):
        """Write a string key/value pair to the output file."""
        assert isinstance(key, str) and isinstance(value, str)

        pos = self.fp.tell()
        self.fp.write(WRITE_2_LE4(len(key), len(value)))
        self.fp.write(key)
        self.fp.write(value)

        h = self.hashfn(key) & 0xffffffff
        self._unordered[h & 0xff].append((h, pos))

    def puts(self, key, values):
        """
        Write more than one value for the same key to the output file.

        Equivalent to calling put() in a loop.
        """
        for value in values:
            self.put(key, value)

    def finalize(self):
        """Write the final hash tables to the output file, and write out its
        index. The output file remains open upon return."""
        index = []
        for tbl in self._unordered:
            length = len(tbl) << 1
            ordered = [(0, 0)] * length
            for pair in tbl:
                where = (pair[0] >> 8) % length
                for i in chain(range(where, length), range(0, where)):
                    if not ordered[i][0]:
                        ordered[i] = pair
                        break

            index.append((self.fp.tell(), length))
            for pair in ordered:
                self.fp.write(WRITE_2_LE4(*pair))

        self.fp.seek(0)
        for pair in index:
            self.fp.write(WRITE_2_LE4(*pair))
        self.fp = None  # prevent double finalize()
