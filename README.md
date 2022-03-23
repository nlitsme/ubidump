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

mounting images on linux
------------------------

    modprobe nandsim first_id_byte=0x2c second_id_byte=0xac third_id_byte=0x90 fourth_id_byte=0x26
    nandwrite /dev/mtd0   firmware-image.ubi 
    modprobe ubi mtd=/dev/mtd0,4096
    mount -t ubifs  -o ro /dev/ubi0_0 mnt

This will mount a ubi image for a device with eraseblock size 0x40000.
If your image has a blocksize of 0x20000, use `fourth_id_byte=0x15`, and specify a pagesize of `2048`
with the second modprobe line.

Usage
=====

```
usage: ubidump.py [-h] [--savedir DIRECTORY] [--preserve] [--cat FILE]
                  [--listfiles] [--dumptree] [--verbose] [--debug]
                  [--encoding ENCODING] [--masteroffset MASTEROFFSET]
                  [--root ROOT] [--rawdump] [--volume VOLUME]
                  [--hexdump LEB:OFF:N] [--nodedump LEB:OFF]
                  FILES [FILES ...]

UBIFS dumper.

positional arguments:
  FILES                 list of ubi images to use

optional arguments:
  -h, --help            show this help message and exit
  --savedir DIRECTORY, -s DIRECTORY
                        save files in all volumes to the specified directory
  --preserve, -p        preserve permissions and timestamps
  --cat FILE, -c FILE   extract a single file to stdout
  --listfiles, -l       list directory contents
  --dumptree, -d        dump the filesystem b-tree contents
  --verbose, -v         print extra info
  --debug               abort on exceptions
  --encoding ENCODING, -e ENCODING
                        filename encoding, default=utf-8
  --masteroffset MASTEROFFSET, -m MASTEROFFSET
                        Which master node to use.
  --root ROOT, -R ROOT  Which Root node to use (hexlnum:hexoffset).
  --rawdump             Raw hexdump of entire volume.
  --volume VOLUME       which volume to hexdump
  --hexdump LEB:OFF:N   hexdump part of a volume/leb[/ofs[/size]]
  --nodedump LEB:OFF    dump specific node at volume/leb[/ofs]
```

Usage Examples
--------------

View the contents of the `/etc/passwd` file in the filesystem image `image.ubi`:

    python ubidump.py  -c /etc/passwd  image.ubi

List the files in all the volumes in `image.ubi`:

    python ubidump.py  -l  image.ubi

View the contents of b-tree database from the volumes in `image.ubi`:

    python ubidump.py  -d  image.ubi


Install
=======

Install the required python modules using:

    pip install -r requirements.txt

or as a pip package:

    pip install ubidump

You may need to manually install your operarating system libraries for lzo first:

on linux:

    apt install liblzo2-dev

on MacOS:

    brew install lzo

maybe you need to build the python library like this:

    LDFLAGS=-L/usr/local/lib CFLAGS=-I/usr/local/include/lzo pip3 install python-lzo


When you need zstd compression, you will need to install the `zstandard` module.


Dependencies
============

 * python2 or python3
 * python-lzo  ( >= 1.09, which introduces the 'header=False' argument )
 * crcmod
 * optional: zstandard

TODO
====

 * add option to select a volume
 * add option to select a older `master` node
 * parse the journal
 * analyze b-tree structure for unused nodes
 * analyze fs structure for unused inodes, dirents
 * verify that data block size equals the size mentioned in the inode.
 * add support for ubifs ( without the ubi layer )
 * add option to extract a raw volume.

References
==========

 * the ubifs/mtd tools http://linux-mtd.infradead.org/
 * git repos can be found [here](http://git.infradead.org/)

Similar tools
=============

 * another python tool  [on github](https://github.com/jrspruitt/ubi_reader/)
     * does not support listing files.
 * a closed source windows tool [here](http://ubidump.oozoon.de/)
 * ubi-utils/ubidump.c [on the mtd mailinglist](http://lists.infradead.org/pipermail/linux-mtd/2014-July/054547.html)

Author
======

Willem Hengeveld <itsme@xs4all.nl>

