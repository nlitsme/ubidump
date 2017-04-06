UBIFS Dumper
============

This tool can be used to view or extract the contents of UBIFS images.

About UBIFS
===========

UBIFS is a filesystem specifically designed for used on NAND flash chips.
NAND flash is organized in _eraseblocks_. _Eraseblocks_ can be erased,
appended to, and read. Erasing is a relatively expensive operation, and can
be done only a limited number of times.

An UBIFS image contains four abstraction layers:
 * eraseblocks
 * volumes
 * b-tree nodes
 * inodes

Each eraseblock contains info on how often it has been erased, and which volume it belongs to.
A volume contains a b-tree database with keys for:
 * inodes, indexed by inode number
 * direntries, indexed by inode number + name hash
 * datablocks, indexed by inode number + block number

The inodes are basically a standard unix filesystem, with direntries, regular files, symlinks, devices, etc.

Usage
=====

View the contents of the `/etc/passwd` file in the filesystem image `image.ubi`:

    python ubidump.py  -c /etc/passwd  image.ubi

List the files in all the volumes in `image.ubi`:

    python ubidump.py  -l  image.ubi

View the contents of b-tree database from the volumes in `image.ubi`:

    python ubidump.py  -d  image.ubi


Dependencies
============

 * python2
 * python-lzo
 * crcmod

TODO
====

 * add option to select a volume
 * add option to select a older `master` node
 * parse the journal
 * analyze b-tree structure for unused nodes
 * analyze fs structure for unused inodes, dirents
 * verify that data block size equals the size mentioned in the inode.
 * automatically determine blocksize

Author
======

Willem Hengeveld <itsme@xs4all.nl>

