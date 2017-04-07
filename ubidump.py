"""
Tool for listing and extracting data from an UBI (Unsorted Block Image) image.

(C) 2017 by Willem Hengeveld <itsme@xs4all.nl>
"""
from __future__ import division, print_function
import crcmod.predefined
import argparse
import struct
from binascii import b2a_hex
import lzo
import zlib
import os
import errno
import datetime
import sys
from collections import defaultdict

if sys.version_info[0] == 3:
    def cmp(a,b):
        return (a>b) - (a<b)

crc32 = crcmod.predefined.mkPredefinedCrcFun('CrcJamCrc')

########### block level objects ############

class UbiEcHeader:
    """
    The Erase count header
    """
    hdrsize = 16*4
    def __init__(self):
        pass
    def parse(self, data):
        self.magic, self.version, self.erasecount, self.vid_hdr_ofs, self.data_ofs, \
                self.image_seq, hdr_crc = struct.unpack(">4sB3xQLLL32xL", data)
        if self.magic != b'UBI#':
            raise Exception("magic num mismatch")
        if hdr_crc != crc32(data[:-4]):
            raise Exception("crc mismatch")
    def __repr__(self):
        return "EC: magic=%s, v%d, ec=%d, vidhdr=%x, data=%x, imgseq=%x" % ( 
                self.magic, self.version, self.erasecount, self.vid_hdr_ofs,
                self.data_ofs, self.image_seq)


VTBL_VOLID=0x7fffefff
class UbiVidHead:
    """
    The volume id header
    """
    hdrsize = 16*4
    def __init__(self):
        self.vol_id = VTBL_VOLID
    def parse(self, data):
        self.magic, self.version, self.vol_type, self.copy_flag, self.compat, self.vol_id, \
                self.lnum, self.data_size, self.used_ebs, self.data_pad, self.data_crc, \
                self.sqnum, hdr_crc = struct.unpack(">4s4BLL4x4L4xQ12xL", data)
        if self.magic != b'UBI!':
            raise Exception("magic num mismatch")
        if hdr_crc != crc32(data[:-4]):
            raise Exception("crc mismatch")
    def __repr__(self):
        if hasattr(self, 'magic'):
            return "VID: magic=%s, v%d, vt=%d, cp=%d, compat=%d, volid=%x, lnum=[%d], " \
                    "dsize=%d, usedebs=%d, datapad=%d, datacrc=%x, sqnum=%d" % (
                            self.magic, self.version, self.vol_type, self.copy_flag, self.compat,
                            self.vol_id, self.lnum, self.data_size, self.used_ebs, self.data_pad,
                            self.data_crc, self.sqnum)
        else:
            return "VID"


class UbiVtblRecord:
    """
    A volume table record.
    """
    hdrsize = 4*4+128+24+4
    def __init__(self):
        self.reserved_pebs = 0
    def parse(self, data):
        self.reserved_pebs, self.alignment, self.data_pad, self.vol_type, self.upd_marker, \
                name_len, self.name, self.flags, crc = struct.unpack(">3LBBH128sB23xL", data)
        if crc != crc32(data[:-4]):
            raise Exception("crc mismatch")
        self.name = self.name[:name_len]
    def empty(self):
        if hasattr(self, 'name'):
            return self.reserved_pebs==0 and self.alignment==0 and self.data_pad==0 \
                    and self.vol_type==0 and self.upd_marker==0 and self.name==b'' and self.flags==0
        else:
            return True

    def __repr__(self):
        return "VREC: rsvpebs=%d, align=%d, datapad=%d, voltype=%d, updmark=%d, flags=%x, name=%s" % (
                self.reserved_pebs, self.alignment, self.data_pad, self.vol_type, 
                        self.upd_marker, self.flags, self.name)


class UbiVolume:
    """
    provides read access to a specific volume in an UBI image.
    """
    def __init__(self, blks, volid, dataofs):
        self.blks = blks
        self.volid = volid
        self.dataofs = dataofs

    def read(self, lnum, offs, size):
        return self.blks.readvolume(self.volid, lnum, self.dataofs+offs, size)


class UbiBlocks:
    """
    Block level access to an UBI image.
    """
    def __init__(self, fh):
        self.fh = fh
        self.lebsize = self.find_blocksize()

        fh.seek(0, 2)
        self.filesize = fh.tell()
        self.maxlebs = self.filesize // self.lebsize

        self.scanblocks()

        if not VTBL_VOLID in self.vmap:
            print("no volume directory, %d physical volumes" % len(self.vmap))
            return
        self.scanvtbls(self.vmap[VTBL_VOLID][0])

        print("%d named volumes found, %d physical volumes, blocksize=0x%x" % (len(self.vbyname), len(self.vmap), self.lebsize))

    def find_blocksize(self):
        self.fh.seek(0)
        magic = self.fh.read(4)
        if magic != b'UBI#':
            raise Exception("not an UBI image")
        for log_blocksize in range(10,20):
            self.fh.seek(1<<log_blocksize)
            magic = self.fh.read(4)
            if magic == b'UBI#':
                return 1<<log_blocksize
        raise Exception("Could not determine UBI image blocksize")

    def scanblocks(self):
        """
        creates map of volid + lnum => physical lnum
        """
        self.vmap = defaultdict(lambda : defaultdict(int))
        for lnum in range(self.maxlebs):

            try:
                ec = UbiEcHeader()
                hdr = self.readblock(lnum, 0, ec.hdrsize)
                ec.parse(hdr)

                vid = UbiVidHead()
                viddata = self.readblock(lnum, ec.vid_hdr_ofs, vid.hdrsize)
                vid.parse(viddata)

                self.vmap[vid.vol_id][vid.lnum] = lnum
            except:
                pass

    def readblock(self, lnum, offs, size):
        self.fh.seek(lnum * self.lebsize + offs)
        return self.fh.read(size)

    def scanvtbls(self, lnum):
        """
        reads the volume table
        """
        ec = UbiEcHeader()
        hdr = self.readblock(lnum, 0, ec.hdrsize)
        ec.parse(hdr)

        self.ec = ec

        try:
            vid = UbiVidHead()
            viddata = self.readblock(lnum, ec.vid_hdr_ofs, vid.hdrsize)
            vid.parse(viddata)

            self.vid = vid

            self.vtbl = []
            self.vbyname = dict()

            if vid.vol_id == VTBL_VOLID:
                for i in range(128):
                    vrec = UbiVtblRecord()
                    vrecdata = self.readblock(lnum, self.ec.data_ofs + i * vrec.hdrsize, vrec.hdrsize)
                    vrec.parse(vrecdata)

                    self.vtbl.append(vrec)

                    if not vrec.empty():
                        self.vbyname[vrec.name] = i
        except:
            print(ec)
            print("viddata:%s" % b2a_hex(viddata))
            import traceback
            traceback.print_exc()

            self.vid = UbiVidHead()
            self.vtbl = [ UbiVtblRecord() ]

    def dumpvtbl(self):
        print("%s  %s" % (self.ec, self.vid))
        for v in self.vtbl:
            if not v.empty():
                print("  %s" % v)

        for volid, lmap in self.vmap.items():
            print("volume %x : %d lebs" % (volid, len(lmap)))

    def nr_volumes(self):
        return len(self.vbyname)
    def getvrec(self, volid):
        return self.vtbl[volid]

    def getvolume(self, volid):
        return UbiVolume(self, volid, self.ec.data_ofs)

    def readvolume(self, volid, lnum, offs, size):
        physlnum = self.vmap[volid].get(lnum, None)
        if physlnum is None:
            raise Exception("volume does not contain lnum")
        return self.readblock(physlnum, offs, size)


################ filesytem level objects ##################

"""
key format:  (inum, (type<<29) | value)
   
key types: UBIFS_*_KEY, INO, DATA, DENT, XENT

inode:  <inum>  + 0
dirent:  <inum>  + hash
xent:  <inum>  + hash
data:  <inum + blocknum
trunc:  <inum>  + 0

"""
def unpackkey(key):
    if len(key)==16 and key[8:]!=b'\x00'*8:
        print("key has more than 8 bytes: %s" % b2a_hex(key))
    inum, value = struct.unpack("<LL", key[:8])
    return (inum, value>>29, value&0x1FFFFFFF)
def packkey(key):
    inum, ityp, value = key
    return struct.pack("<LL", inum, (ityp<<29) | value)
def formatkey(key):
    if key is None:
        return "None"
    if type(key) != tuple:
        key = unpackkey(key)
    return "%05d:%d:%08x" % key
def comparekeys(lhs, rhs):
    return cmp(unpackkey(lhs), unpackkey(rhs))

def namehash(name):
    a = 0
    for b in name:
        if type(b)==str: b = ord(b)
        a += b<<4
        a += b>>4
        a &= 0xFFFFFFFF
        a *= 11
        a &= 0xFFFFFFFF
    a &= 0x1FFFFFFF
    if a <= 2: a += 3
    return a

def unlzo(data, buflen):
    return lzo.decompress(data, False, buflen)
def unzlib(data):
    return zlib.decompress(data)

def decompress(data, buflen, compr_type):
    if compr_type==0:
        return data
    elif compr_type==1:
        return unlzo(data, buflen)
    elif compr_type==2:
        return unzlib(buflen)
    else:
        raise Exception("unknown compression type")

# the blocksize is a fixed value, independent of the underlying device.
UBIFS_BLOCKSIZE = 4096

########### objects for the various node types ########### 
class UbiFsInode:
    nodetype = 0
    hdrsize = 16 + 5*8 + 11*4 + 2*4 + 28
    def __init__(self):
        pass
    def parse(self, data):
        self.key, self.creat_sqnum, self.size, self.atime_sec, self.ctime_sec, self.mtime_sec, \
                self.atime_nsec, self.ctime_nsec, self.mtime_nsec, self.nlink, self.uid, self.gid, \
                self.mode, self.flags, self.data_len, self.xattr_cnt, self.xattr_size, \
                self.xattr_names, self.compr_type = struct.unpack("<16s5Q11L4xLH26x", data[:self.hdrsize])

        # data contains the symlink string for symbolic links
        self.data = data[self.hdrsize:]
        if len(self.data) != self.data_len:
            raise Exception("inode data size mismatch")

    def inodedata_repr(self):
        types = ["0", "FIFO", "CHAR", "3", "DIRENT", "5", "BLOCK", "7", "FILE", "9", "LINK", "11", "SOCK", "13", "14", "15"]
        typ = (self.mode>>12)&0xF
        if typ in (2, 6):
            return types[typ] + ":" + b2a_hex(self.data)
        return types[typ] + ":" + self.data

    def __repr__(self):
        return "INODE: key=%s, sq=%04x, size=%5d, n=%3d, uid:gid=%d:%d, mode=%06o, fl=%x, dl=%3d, " \
                "xattr=%d:%d, xanames=%d, comp=%d -- %s" % (formatkey(self.key), self.creat_sqnum, 
                        self.size, self.nlink, self.uid, self.gid, self.mode, self.flags, self.data_len, 
                        self.xattr_cnt, self.xattr_size, self.xattr_names, self.compr_type,  self.inodedata_repr())
        # todo: self.atime_sec, self.ctime_sec, self.mtime_sec, self.atime_nsec, self.ctime_nsec, self.mtime_nsec, 


class UbiFsData:
    nodetype = 1
    hdrsize = 16 + 4 + 4
    def __init__(self):
        pass
    def parse(self, data):
        self.key, self.size, self.compr_type = struct.unpack("<16sLH2x", data[:self.hdrsize])
        self.data = decompress(data[self.hdrsize:], self.size, self.compr_type)
        if len(self.data) != self.size:
            raise Exception("data size mismatch")
    def __repr__(self):
        return "DATA: key=%s, size=%d, comp=%d" % (formatkey(self.key), self.size, self.compr_type)


class UbiFsDirEntry:
    TYPE_REGULAR = 0
    TYPE_DIRECTORY = 1
    TYPE_SYMLINK = 2
    TYPE_BLOCKDEV = 3
    TYPE_CHARDEV = 4
    TYPE_FIFO = 5
    TYPE_SOCKET = 6

    ALL_TYPES = 127

    nodetype = 2
    hdrsize = 16 + 8+4+4
    def __init__(self):
        pass
    def parse(self, data):
        self.key, self.inum, self.type, nlen = struct.unpack("<16sQxBH4x", data[:self.hdrsize])
        self.name = data[self.hdrsize:-1]
        if len(self.name) != nlen:
            raise Exception("name length mismatch")
    def __repr__(self):
        typenames = [ 'reg', 'dir', 'lnk', 'blk', 'chr', 'fifo', 'sock' ]
        # type: UBIFS_ITYPE_REG, UBIFS_ITYPE_DIR, etc
        return "DIRENT: key=%s, inum=%05d, type=%d:%s -- %s" % (formatkey(self.key), self.inum, self.type, typenames[self.type], self.name)


class UbiFsExtendedAttribute:
    nodetype = 3
    hdrsize = 0
    def __init__(self):
        pass
    def parse(self, data):
        struct.unpack("<", data)
    def __repr__(self):
        return "EA"


class UbiFsTruncation:
    nodetype = 4
    hdrsize = 4+12+2*8
    def __init__(self):
        pass
    def parse(self, data):
        self.inum, self.old_size, self.new_size = struct.unpack("<L12xQQ", data)
    def __repr__(self):
        return "TRUNC: inum:%05d, size:%d->%d" % (self.inum, self.old_size, self.new_size)


class UbiFsPadding:
    nodetype = 5
    hdrsize = 4
    def __init__(self):
        pass
    def parse(self, data):
        self.pad_len, = struct.unpack("<L", data)
    def __repr__(self):
        return "PAD: padlen=%d" % self.pad_len


class UbiFsSuperblock:
    nodetype = 6
    hdrsize = 6*4+8+7*4+3*4+8+4+16+4
    def __init__(self):
        pass
    def parse(self, data):
        self.key_hash, self.key_fmt, self.flags, self.min_io_size, self.leb_size, self.leb_cnt, \
                self.max_leb_cnt, self.max_bud_bytes, self.log_lebs, self.lpt_lebs, self.orph_lebs, \
                self.jhead_cnt, self.fanout, self.lsave_cnt, self.fmt_version, self.default_compr, \
                self.rp_uid, self.rp_gid, self.rp_size, self.time_gran, self.uuid, self.ro_compat_version \
            = struct.unpack("<2xBB5LQ7LH2xLLQL16sL", data[:self.hdrsize])
        if len(data) != self.hdrsize + 3968:
            raise Exception("invalid superblock padding size")
    def __repr__(self):
        return "SUPER: kh:%d, fmt:%d, flags=%x, minio=%d, lebsize=0x%x, lebcount=%d, maxleb=%d, " \
                "maxbud=%d, loglebs=%d, lptlebs=%d, orphlebs=%d, jheads=%d, fanout=%d, lsave=%d, " \
                "fmt=v%d, compr=%d, rp=%d:%d, rpsize=%d, timegran=%d, uuid=%s, rocompat=%d" % (
                        self.key_hash, self.key_fmt, self.flags, self.min_io_size, self.leb_size,
                        self.leb_cnt, self.max_leb_cnt, self.max_bud_bytes, self.log_lebs, self.lpt_lebs,
                        self.orph_lebs, self.jhead_cnt, self.fanout, self.lsave_cnt, self.fmt_version,
                        self.default_compr, self.rp_uid, self.rp_gid, self.rp_size, self.time_gran,
                        b2a_hex(self.uuid), self.ro_compat_version)


class UbiFsMaster:
    nodetype = 7
    hdrsize = 2*8+8*4+6*8+12*4
    def __init__(self):
        pass
    def parse(self, data):
        self.highest_inum, self.cmt_no, self.flags, self.log_lnum, self.root_lnum, self.root_offs, \
                self.root_len, self.gc_lnum, self.ihead_lnum, self.ihead_offs, self.index_size, \
                self.total_free, self.total_dirty, self.total_used, self.total_dead, \
                self.total_dark, self.lpt_lnum, self.lpt_offs, self.nhead_lnum, self.nhead_offs, \
                self.ltab_lnum, self.ltab_offs, self.lsave_lnum, self.lsave_offs, self.lscan_lnum, \
                self.empty_lebs, self.idx_lebs, self.leb_cnt = struct.unpack("<QQ8L6Q12L", data[:self.hdrsize])
        if len(data) != self.hdrsize + 344:
            raise Exception("invalid master padding size")
    def __repr__(self):
        return "MST: max_inum=%05d, cmtno=%d, flags=%x, loglnum=%d, root=[%02d:0x%05x], rootlen=%d, " \
                "gc_lnum=[%d], ihead=[%02d:0x%05x], ixsize=%d, total(free:%d, dirty:%d, used:%d, " \
                "dead:%d, dark:%d), lpt=[%02d:0x%05x], nhead=[%02d:0x%05x], ltab=[%02d:0x%05x], " \
                "lsave=[%02d:0x%05x], lscan=[%d], empty=%d, idx=%d, nleb=%d" % (
                        self.highest_inum, self.cmt_no, self.flags, self.log_lnum, self.root_lnum,
                        self.root_offs, self.root_len, self.gc_lnum, self.ihead_lnum, self.ihead_offs,
                        self.index_size, self.total_free, self.total_dirty, self.total_used, self.total_dead,
                        self.total_dark, self.lpt_lnum, self.lpt_offs, self.nhead_lnum, self.nhead_offs,
                        self.ltab_lnum, self.ltab_offs, self.lsave_lnum, self.lsave_offs, self.lscan_lnum,
                        self.empty_lebs, self.idx_lebs, self.leb_cnt)


class UbiFsLEBReference:
    nodetype = 8
    hdrsize = 12+28
    def __init__(self):
        pass
    def parse(self, data):
        self.lnum, self.offs, self.jhead = struct.unpack("<3L28x", data)
    def __repr__(self):
        return "REF: ref=[%02d:0x%05x], jhead=%d" % (self.lnum, self.offs, self.jhead)


class UbiFsIndex:
    nodetype = 9
    hdrsize = 4

    class Branch:
        hdrsize = 12
        def __init__(self):
            pass
        def parse(self, data):
            self.lnum, self.offs, self.len = struct.unpack("<3L", data[:self.hdrsize])
            self.key = data[self.hdrsize:]
        def __repr__(self):
            return "BRANCH: ref=[%02d:0x%05x] len=%4d -- key=%s" % (self.lnum, self.offs, self.len, formatkey(self.key))

    def __init__(self):
        pass
    def parse(self, data):
        self.child_cnt, self.level = struct.unpack("<HH", data[:self.hdrsize])
        self.branches = []
        o = self.hdrsize
        for _ in range(self.child_cnt):
            if o >= len(data):
                raise Exception("parse error")
            branch = self.Branch()
            branch.parse(data[o:o+branch.hdrsize])  ; o += branch.hdrsize
            branch.key = data[o:o+8]     ; o += 8
            self.branches.append(branch)
    def __repr__(self):
        return "INDEX: nchild=%d, level=%d" % (self.child_cnt, self.level)


    def find(self, key):
        """
        searches index for a branch.key >= key, returns relation to the key

        these are all possibilities with 1 branches

            key < b0    -> 'lt', 0
            key == b0   -> 'eq', 0
            b0 < key    -> 'gt', 0

        these are all possibilities with 2 branches
            key < b0 < b1   -> 'lt', 0
            key == b0 < b1  -> 'eq', 0
            b0 < key < b1   -> 'gt', 0
            b0 < key == b1  -> 'eq', 1
            b0 < b1 < key   -> 'gt', 1

        add two more options for every next branch.

        """
        for i, b in enumerate(self.branches):
            c = comparekeys(key, b.key)
            if c<0:
                if i==0:
                    # before first item
                    return ('lt', i)
                else:
                    # between prev and this item
                    return ('gt', i-1)
            elif c==0:
                # found item
                return ('eq', i)
            # else c>0 -> continue searching

        # after last item
        return ('gt', i)



class UbiFsCommitStart:
    nodetype = 10
    hdrsize = 8
    def __init__(self):
        pass
    def parse(self, data):
        self.cmt_no, = struct.unpack("<Q", data[:self.hdrsize])
    def __repr__(self):
        return "COMMIT: cmt=%d" % self.cmt_no


class UbiFsOrphan:
    nodetype = 11
    hdrsize = 8
    def __init__(self):
        pass
    def parse(self, data):
        self.cmt_no, = struct.unpack("<Q", data[:self.hdrsize])
        # todo: inos
    def __repr__(self):
        return "ORPHAN: cmt=%d" % self.cmt_no


class UbiFsCommonHeader:
    hdrsize = 16+8
    _classmap = [
            UbiFsInode,                 #  0
            UbiFsData,                  #  1
            UbiFsDirEntry,              #  2
            UbiFsExtendedAttribute,     #  3
            UbiFsTruncation,            #  4
            UbiFsPadding,               #  5
            UbiFsSuperblock,            #  6
            UbiFsMaster,                #  7
            UbiFsLEBReference,          #  8
            UbiFsIndex,                 #  9
            UbiFsCommitStart,           # 10
            UbiFsOrphan,                # 11
    ]
    def __init__(self):
        pass
    def parse(self, data):
        self.magic, self.crc, self.sqnum, self.len, self.node_type, self.group_type = struct.unpack("<LLQLBB2x", data)
        if self.magic != 0x06101831:
            raise Exception("magic num mismatch")

    def getnode(self):
        """
        create node object for current node type.
        """
        if 0 <= self.node_type < len(self._classmap):
            cls = self._classmap[self.node_type]

            node = cls()
            node.hdr = self

            return node
        raise Exception("invalid node type")


class UbiFs:
    """
    Filesystem level access to an UBI image volume.

    the filesystem consists of a b-tree containing inodes, direntry and data nodes.
    """
    def __init__(self, vol):
        """
        The constructor takes a UbiVolume object
        """
        self.vol = vol

        self.load()

    def find_most_recent_master(self):
        o = 0
        while True:
            try:
                mst = self.readnode(1, o)
                o += 0x1000   # Fixed value ... do i need to configure this somewhere?
            except:
                return mst

    def load(self):
        self.sb = self.readnode(0, 0)
        self.mst = self.find_most_recent_master()

        # todo: check that the 2nd master node matches the first.
        #mst2 = self.readnode(2, 0)

        self.root = self.readnode(self.mst.root_lnum, self.mst.root_offs)

    def dumpfs(self):
        print("*** superblock ***\n%s" % self.sb)
        print("*** masterblock ***\n%s" % self.mst)

    def readnode(self, lnum, offs):
        """
        read a node from a lnum + offset.
        """
        ch = UbiFsCommonHeader()
        hdrdata = self.vol.read(lnum, offs, ch.hdrsize)
        ch.parse(hdrdata)

        ch.lnum = lnum
        ch.offs = offs

        node = ch.getnode()
        nodedata = self.vol.read(lnum, offs + ch.hdrsize, ch.len - ch.hdrsize)

        if crc32(hdrdata[8:] + nodedata) != ch.crc:
            print(ch, node)
            print(" %s + %s = %08x -> want = %08x" % ( b2a_hex(hdrdata), b2a_hex(nodedata), crc32(hdrdata[8:] + nodedata), ch.crc))
            raise Exception("invalid node crc")
        node.parse(nodedata)

        return node

    def printrecursive(self, idx):
        """
        Recursively dump all b-tree nodes.
        """
        if not hasattr(idx, 'branches'):
            print(idx)
            return
        print("[%2d:0x%05x] %s" % (idx.hdr.lnum, idx.hdr.offs, idx))
        for i, b in enumerate(idx.branches):
            print("%s %d %s -> " % ("  " * (6-idx.level), i, b), end=" ")
            try:
                n = self.readnode(b.lnum, b.offs)
                self.printrecursive(n)
            except Exception as e:
                print("ERROR %s" % e)

    class Cursor:
        """
        The Cursor represents a position in the b-tree.
        """
        def __init__(self, fs, stack):
            self.fs = fs
            self.stack = stack
        def next(self):
            """ move cursor to next entry """
            if not self.stack:
                # starting at 'eof'
                page = self.fs.root
                ix = 0
            else:
                page, ix = self.stack.pop()
                while self.stack and ix==len(page.branches)-1:
                    page, ix = self.stack.pop()
                if ix==len(page.branches)-1:
                    return
                ix += 1
            self.stack.append( (page, ix) )
            while page.level:
                page = self.fs.readnode(page.branches[ix].lnum, page.branches[ix].offs)
                ix = 0
                self.stack.append( (page, ix) )
        def prev(self):
            """ move cursor to next entry """
            if not self.stack:
                # starting at 'eof'
                page = self.fs.root
                ix = len(page.branches)-1
            else:
                page, ix = self.stack.pop()
                while self.stack and ix==0:
                    page, ix = self.stack.pop()
                if ix==0:
                    return
                ix -= 1
            self.stack.append( (page, ix) )
            while page.level:
                page = self.fs.readnode(page.branches[ix].lnum, page.branches[ix].offs)
                ix = len(page.branches)-1
                self.stack.append( (page, ix) )
        def eof(self):
            return len(self.stack)==0
        def __repr__(self):
            return "[%s]" % (",".join(str(_[1]) for _ in self.stack))

        def getkey(self):
            """
            Returns the key tuple for the current item
            """
            if self.stack:
                page, ix = self.stack[-1]
                return unpackkey(page.branches[ix].key)
        def getnode(self):
            """
            Returns the node object for the current item
            """
            if self.stack:
            if self.stack:
                page, ix = self.stack[-1]
                return self.fs.readnode(page.branches[ix].lnum, page.branches[ix].offs)


    def find(self, rel, key):
        """
        returns a cursor for the relation + key.

        ('lt', searchkey) searches for the highest ordered node with a key less than `searchkey`
        ('ge', searchkey) searches for the lowest ordered node with a key greater or equal to `searchkey`
        etc...

        """
        stack = []
        page = self.root
        while len(stack)<32:
            act, ix = page.find(packkey(key))
            stack.append( (page, ix) )
            if page.level==0:
                break
            page = self.readnode(page.branches[ix].lnum, page.branches[ix].offs)
        if len(stack)==32:
            raise Exception("tree too deep")

        cursor = self.Cursor(self, stack)

        """
        act                  rel:  | lt       le      eq        ge       gt
        (lt, 0)  key < 0           | None     None   None      pass     pass
        (eq, ix) key == ix         |  --      pass   pass      pass      ++
        (gt, ix) ix < key < ix+1   | pass     pass   None       ++       ++
        """

        if (act+rel) in ('gtlt', 'gtle', 'eqle', 'eqeq', 'eqge', 'ltge', 'ltgt'):
            return cursor
        if (act+rel) in ('ltlt', 'ltle', 'lteq', 'gteq'):
            return None
        if (act+rel) == 'eqlt':
            cursor.prev()
            return cursor
        if (act+rel) in ('eqgt', 'gtge', 'gtgt'):
            cursor.next()
            return cursor

        raise Exception("unexpected case")


    def recursefiles(self, inum, path, filter = 1<<UbiFsDirEntry.TYPE_REGULAR):
        """
        Recursively yield all files below the directory with inode `inum`
        """
        startkey = (inum, 2, 0)
        endkey = (inum, 3, 0)
        c = self.find('ge', startkey)
        while not c.eof() and c.getkey() < endkey:
            ent = c.getnode()

            if filter & (1<<ent.type):
                yield ent.inum, path + [ent.name]
            if ent.type==ent.TYPE_DIRECTORY:
                # recurse into subdirs
                for x in self.recursefiles(ent.inum, path + [ent.name], filter):
                    yield x

            c.next()

    def savefile(self, inum, fh, ubiname):
        """
        save file data from inode `inum` to the filehandle `fh`.

        the `ubiname` argument is not needed, except for printing useful error messages.
        """
        startkey = (inum, 1, 0)
        endkey = (inum, 2, 0)
        c = self.find('ge', startkey)

        savedlen = 0
        while not c.eof() and c.getkey() < endkey:
            dat = c.getnode()
            _, _, blocknum = c.getkey()

            fh.seek(UBIFS_BLOCKSIZE * blocknum)

            fh.write(dat.data)
            savedlen += len(dat.data)

            c.next()

        c = self.find('eq', (inum, 0, 0))
        inode = c.getnode()
        if savedlen > inode.size:
            print("WARNING: found more (%d bytes) for inode %05d, than specified in the inode(%d bytes) -- %s" % (savedlen, inum, inode.size, ubiname))
        elif savedlen < inode.size:
            # padding file with zeros
            fh.seek(inode.size)
            fh.truncate(inode.size)

    def findfile(self, path, inum = 1):
        """
        find the inode of the given `path`, starting in the directory specified by `inum`

        `path` must be a list of path elements. ( so not a '/' separated path string )
        """
        itype = UbiFsDirEntry.TYPE_DIRECTORY
        for part in path:
            if itype!=UbiFsDirEntry.TYPE_DIRECTORY:
                # not a directory
                return None
            c = self.find('eq', (inum, 2, namehash(part)))
            if not c or c.eof():
                # not found
                return None
            dirent = c.getnode()
            inum, itype = dirent.inum, dirent.type
        return inum


def modestring(mode):
    """
    return a "-rw-r--r--" style mode string
    """
    # 4 bits type
    # 3 bits suid/sgid/sticky
    # 3 bits owner perm
    # 3 bits group perm
    # 3 bits other perm
    typechar = "?pc?d?b?-?l?s???"

    def rwx(bits, extra, xchar):
        rflag = "-r"[(bits>>2)&1]
        wflag = "-w"[(bits>>1)&1]
        xflag = ("-x" + xchar.upper() + xchar.lower())[(bits&1)+2*extra]

        return rflag + wflag + xflag

    return typechar[mode>>12] + rwx((mode>>6)&7, (mode>>11)&1, 's') + rwx((mode>>3)&7, (mode>>10)&1, 's') + rwx(mode&7, (mode>>9)&1, 't')

def timestring(t):
    return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


def processfile(fn, args):
    """
    Perform actions specified by `args` on the ubi image in the file `fn`
    """
    with open(fn, "rb") as fh:
        blks = UbiBlocks(fh)
        if args.verbose:
            print("===== block =====")
            blks.dumpvtbl()

        for volid in range(blks.nr_volumes()):
            vrec = blks.getvrec(volid)
            vol = blks.getvolume(volid)

            print("== volume %s ==" % vrec.name)

            fs = UbiFs(vol)
            if args.verbose:
                fs.dumpfs()
            if args.dumptree:
                fs.printrecursive(fs.root)
            if args.savedir:
                count = 0
                for inum, path in fs.recursefiles(1, []):
                    try:
                        os.makedirs(os.path.join(*[args.savedir, vrec.name] + path[:-1]))
                    except OSError as e:
                        # be happy if someone already created the path
                        if e.errno != errno.EEXIST:
                            raise

                    with open(os.path.join(*[args.savedir, vrec.name] + path), "wb") as fh:
                        fs.savefile(inum, fh, os.path.join(path))

                    count += 1
                print("saved %d files" % count)
            if args.listfiles:
                for inum, path in fs.recursefiles(1, [], UbiFsDirEntry.ALL_TYPES):
                    c = fs.find('eq', (inum, 0, 0))
                    inode = c.getnode()

                    if (inode.mode>>12) in (2, 6):
                        ma, mi = struct.unpack("BB", inode.data[:2])
                        sizestr = "%d,%4d" % (ma, mi)
                    else:
                        sizestr = str(inode.size)

                    if (inode.mode>>12) == 10:
                        linkstr = " -> %s" % inode.data
                    else:
                        linkstr = ""

                    print("%s %2d %-5d %-5d %10s %s %s%s" % (modestring(inode.mode), inode.nlink, inode.uid, inode.gid, sizestr, timestring(inode.mtime_sec), "/".join(path), linkstr))
            if args.cat:
                inum = fs.findfile(args.cat.lstrip('/').split('/'))
                if inum:
                    fs.savefile(inum, sys.stdout, args.cat)


def main():
    parser = argparse.ArgumentParser(description='UBIFS dumper.')
    parser.add_argument('--savedir', '-s',  type=str, help="save files in all volumes to the specified directory", metavar='DIRECTORY')
    parser.add_argument('--cat', '-c',  type=str, help="extract a single file to stdout", metavar='FILE')
    parser.add_argument('--listfiles', '-l',  action='store_true', help="list directory contents")
    parser.add_argument('--dumptree', '-d',  action='store_true', help="dump the filesystem b-tree contents")
    parser.add_argument('--verbose', '-v',  action='store_true', help="print extra info")
    parser.add_argument('FILES',  type=str, nargs='+', help="list of ubi images to use")
    args = parser.parse_args()

    for fn in args.FILES:
        print("==>", fn, "<==")
        try:
            processfile(fn, args)
        except Exception as e:
            print("ERROR", e)
            import traceback
            if args.verbose:
                traceback.print_exc()


if __name__ == '__main__':
    main()
