# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""DRM library wrapper.

Based on:
  third_party/autotest/files/client/cros/graphics/drm.py

A wrapper around the Direct Rendering Manager (DRM) library, which itself is a
wrapper around the Direct Rendering Interface (DRI) between the kernel and
userland.

Since we are masochists, we use ctypes instead of cffi to load libdrm and
access several symbols within it. We use Python's file descriptor and mmap
wrappers.

At some point in the future, cffi could be used, for approximately the same
cost in lines of code.
"""

from ctypes import *
import mmap
import os

from PIL import Image


class DrmVersion(Structure):
    """
    The version of a DRM node.
    """

    _fields_ = [
        ("version_major", c_int),
        ("version_minor", c_int),
        ("version_patchlevel", c_int),
        ("name_len", c_int),
        ("name", c_char_p),
        ("date_len", c_int),
        ("date", c_char_p),
        ("desc_len", c_int),
        ("desc", c_char_p),
    ]

    _l = None

    def __repr__(self):
        return "%s %d.%d.%d (%s) (%s)" % (
            self.name,
            self.version_major,
            self.version_minor,
            self.version_patchlevel,
            self.desc,
            self.date,
        )

    def __del__(self):
        if self._l:
            self._l.drmFreeVersion(self)


class DrmModeResources(Structure):
    """
    Resources associated with setting modes on a DRM node.
    """

    _fields_ = [
        ("count_fbs", c_int),
        ("fbs", POINTER(c_uint)),
        ("count_crtcs", c_int),
        ("crtcs", POINTER(c_uint)),
        # XXX incomplete struct!
    ]

    _fd = None
    _l = None

    def __repr__(self):
        return "<DRM mode resources>"

    def __del__(self):
        if self._l:
            self._l.drmModeFreeResources(self)

    def getCrtc(self, index):
        """
        Obtain the CRTC at a given index.

        @param index: The CRTC to get.
        """

        if not 0 <= index < self.count_crtcs:
            raise IndexError("CRTC index out of range")

        crtc = self._l.drmModeGetCrtc(self._fd, self.crtcs[index]).contents
        crtc._fd = self._fd
        crtc._l = self._l
        return crtc


class DrmModeCrtc(Structure):
    """
    A DRM modesetting CRTC.
    """

    _fields_ = [
        ("crtc_id", c_uint),
        ("buffer_id", c_uint),
        # XXX incomplete struct!
    ]

    _fd = None
    _l = None

    def __repr__(self):
        return "<CRTC (%d)>" % self.crtc_id

    def __del__(self):
        if self._l:
            self._l.drmModeFreeCrtc(self)

    def hasFb(self):
        """
        Whether this CRTC has an associated framebuffer.
        """

        return self.buffer_id != 0

    def fb(self):
        """
        Obtain the framebuffer, if one is associated.
        """

        if self.hasFb():
            fb = self._l.drmModeGetFB(self._fd, self.buffer_id).contents
            fb._fd = self._fd
            fb._l = self._l
            return fb


class drm_mode_map_dumb(Structure):
    """
    Request a mapping of a modesetting buffer.

    The map will be "dumb;" it will be accessible via mmap() but very slow.
    """

    _fields_ = [
        ("handle", c_uint),
        ("pad", c_uint),
        ("offset", c_ulonglong),
    ]


# This constant is not defined in any one header; it is the pieced-together
# incantation for the ioctl that performs dumb mappings. I would love for this
# to not have to be here, but it can't be imported from any header easily.
DRM_IOCTL_MODE_MAP_DUMB = 0xc01064b3


class DrmModeFB(Structure):
    """
    A DRM modesetting framebuffer.
    """

    _fields_ = [
        ("fb_id", c_uint),
        ("width", c_uint),
        ("height", c_uint),
        ("pitch", c_uint),
        ("bpp", c_uint),
        ("depth", c_uint),
        ("handle", c_uint),
    ]

    _l = None
    _map = None

    def __repr__(self):
        s = "<Framebuffer (%dx%d (pitch %d bytes), %d bits/pixel, depth %d)"
        vitals = s % (
            self.width,
            self.height,
            self.pitch,
            self.bpp,
            self.depth,
        )
        if self._map:
            tail = " (mapped)>"
        else:
            tail = ">"
        return vitals + tail

    def __del__(self):
        if self._l:
            self._l.drmModeFreeFB(self)

    def map(self):
        """
        Map the framebuffer.
        """

        if self._map:
            return

        mapDumb = drm_mode_map_dumb()
        mapDumb.handle = self.handle

        rv = self._l.drmIoctl(self._fd, DRM_IOCTL_MODE_MAP_DUMB,
                pointer(mapDumb))
        if rv:
            raise IOError(rv, os.strerror(rv))

        size = self.pitch * self.height

        # mmap.mmap() has a totally different order of arguments in Python
        # compared to C; check the documentation before altering this
        # incantation.
        self._map = mmap.mmap(self._fd, size, flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ, offset=mapDumb.offset)

    def unmap(self):
        """
        Unmap the framebuffer.
        """

        if self._map:
            self._map.close()
            self._map = None


def loadDRM():
    """
    Load a handle to libdrm.

    In addition to loading, this function also configures the argument and
    return types of functions.
    """

    l = cdll.LoadLibrary("libdrm.so")

    l.drmGetVersion.argtypes = [c_int]
    l.drmGetVersion.restype = POINTER(DrmVersion)

    l.drmFreeVersion.argtypes = [POINTER(DrmVersion)]
    l.drmFreeVersion.restype = None

    l.drmModeGetResources.argtypes = [c_int]
    l.drmModeGetResources.restype = POINTER(DrmModeResources)

    l.drmModeFreeResources.argtypes = [POINTER(DrmModeResources)]
    l.drmModeFreeResources.restype = None

    l.drmModeGetCrtc.argtypes = [c_int, c_uint]
    l.drmModeGetCrtc.restype = POINTER(DrmModeCrtc)

    l.drmModeFreeCrtc.argtypes = [POINTER(DrmModeCrtc)]
    l.drmModeFreeCrtc.restype = None

    l.drmModeGetFB.argtypes = [c_int, c_uint]
    l.drmModeGetFB.restype = POINTER(DrmModeFB)

    l.drmModeFreeFB.argtypes = [POINTER(DrmModeFB)]
    l.drmModeFreeFB.restype = None

    l.drmIoctl.argtypes = [c_int, c_ulong, c_voidp]
    l.drmIoctl.restype = c_int

    return l


class DRM:
    """
    A DRM node.
    """

    def __init__(self, library, fd):
        self._l = library
        self._fd = fd

    def __repr__(self):
        return "<DRM (FD %d)>" % self._fd

    @classmethod
    def fromHandle(cls, handle):
        """
        Create a node from a file handle.

        @param handle: A file-like object backed by a file descriptor.
        """

        self = cls(loadDRM(), handle.fileno())
        # We must keep the handle alive, and we cannot trust the caller to
        # keep it alive for us.
        self._handle = handle
        return self

    def version(self):
        """
        Obtain the version.
        """

        v = self._l.drmGetVersion(self._fd).contents
        v._l = self._l
        return v

    def resources(self):
        """
        Obtain the modesetting resources.
        """

        r = self._l.drmModeGetResources(self._fd).contents
        r._fd = self._fd
        r._l = self._l
        return r


def drmFromMinor(minor):
    """
    Given a DRM node number, open the corresponding node.

    @param minor: The number of the minor node to open.
    """

    path = "/dev/dri/card%d" % minor
    handle = open(path)
    return DRM.fromHandle(handle)


def _bgrx24(i):
    b = ord(next(i))
    g = ord(next(i))
    r = ord(next(i))
    next(i)
    return r, g, b


def _screenshot(image, fb):
    fb.map()
    m = fb._map
    lineLength = fb.width * fb.bpp // 8
    pitch = fb.pitch
    pixels = []

    if fb.depth == 24:
        unformat = _bgrx24
    else:
        raise RuntimeError("Couldn't unformat FB: %r" % fb)

    for y in range(fb.height):
        offset = y * pitch
        m.seek(offset)
        channels = m.read(lineLength)
        ichannels = iter(channels)
        for x in range(fb.width):
            rgb = unformat(ichannels)
            image.putpixel((x, y), rgb)

    fb.unmap()

    return pixels


def screenshot():
    """
    Take a screenshot, returning an image object.
    """

    d = drmFromMinor(0)
    fb = d.resources().getCrtc(0).fb()
    image = Image.new("RGB", (fb.width, fb.height))
    pixels = _screenshot(image, fb)

    return image
