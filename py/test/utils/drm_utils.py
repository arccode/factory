# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A Python wrapper of Direct Rendering Manager (DRM) library.

This is a Python wrapper of libdrm, which itself is a wrapper around the Direct
Rendering Interface (DRI) between userland and kernel.

The Python ctypes representation of the following data structures are based on
libdrm-2.4.58: http://dri.freedesktop.org/libdrm/libdrm-2.4.58.tar.bz2
"""

import ctypes
import mmap
import os

from cros.factory.external import PIL
if PIL.MODULE_READY:
  from cros.factory.external.PIL import Image  # pylint: disable=no-name-in-module


class DRMError(Exception):
  """Error raised when accessing DRM."""


class DRMModeBaseStruct(ctypes.Structure):
  """Base class for DRM mode struct classes.

  Attributes:
    fd: the file descriptor of the opened DRM handle.
    need_free: set to True when a instance is created with a call to an allocate
        function in the DRM library, in which case the dtor needs to free the
        allocated memory by calling the corresponding free function.
  """
  fd = None
  need_free = False


class DRMModeResource(DRMModeBaseStruct):
  """C struct of DRM mode resource.

  This is a Python representation of the following C struct in xf86drmMode.h:

    typedef struct _drmModeRes {
            int count_fbs;
            uint32_t *fbs;

            int count_crtcs;
            uint32_t *crtcs;

            int count_connectors;
            uint32_t *connectors;

            int count_encoders;
            uint32_t *encoders;

            uint32_t min_width, max_width;
            uint32_t min_height, max_height;
    } drmModeRes, *drmModeResPtr;
  """
  _fields_ = [
      ('count_fbs', ctypes.c_int),
      ('fbs', ctypes.POINTER(ctypes.c_uint32)),
      ('count_crtcs', ctypes.c_int),
      ('_crtcs', ctypes.POINTER(ctypes.c_uint32)),
      ('count_connectors', ctypes.c_int),
      ('_connectors', ctypes.POINTER(ctypes.c_uint32)),
      ('count_encoders', ctypes.c_int),
      ('encoders', ctypes.POINTER(ctypes.c_uint32)),
      ('min_width', ctypes.c_uint32), ('max_width', ctypes.c_uint32),
      ('min_height', ctypes.c_uint32), ('max_height', ctypes.c_uint32),
  ]

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeResources(ctypes.byref(self))

  @property
  def crtcs(self):
    ret = []
    for i in range(self.count_crtcs):
      crtc = _GetDRMLibrary().drmModeGetCrtc(self.fd, self._crtcs[i]).contents
      crtc.fd = self.fd
      crtc.need_free = True
      ret.append(crtc)
    return ret

  @property
  def connectors(self):
    ret = []
    for i in range(self.count_connectors):
      conn = _GetDRMLibrary().drmModeGetConnector(
          self.fd, self._connectors[i]).contents
      conn.fd = self.fd
      conn.need_free = True
      ret.append(conn)
    return ret


class DRMModeModeInfo(DRMModeBaseStruct):
  """C struct of DRM mode modeinfo.

  This is a Python representation of the following C struct in xf86drmMode.h:

    #define DRM_DISPLAY_MODE_LEN    32
    typedef struct _drmModeModeInfo {
            uint32_t clock;
            uint16_t hdisplay, hsync_start, hsync_end, htotal, hskew;
            uint16_t vdisplay, vsync_start, vsync_end, vtotal, vscan;

            uint32_t vrefresh;

            uint32_t flags;
            uint32_t type;
            char name[DRM_DISPLAY_MODE_LEN];
    } drmModeModeInfo, *drmModeModeInfoPtr;
  """
  DRM_DISPLAY_MODE_LEN = 32
  _fields_ = [
      ('clock', ctypes.c_uint32),
      ('hdisplay', ctypes.c_uint16), ('hsync_start', ctypes.c_uint16),
      ('hsync_end', ctypes.c_uint16), ('htotal', ctypes.c_uint16),
      ('hskew', ctypes.c_uint16),
      ('vdisplay', ctypes.c_uint16), ('vsync_start', ctypes.c_uint16),
      ('vsync_end', ctypes.c_uint16), ('vtotal', ctypes.c_uint16),
      ('vscan', ctypes.c_uint16),
      ('vrefresh', ctypes.c_uint32),
      ('flags', ctypes.c_uint32),
      ('type', ctypes.c_uint32),
      ('name', ctypes.c_char * DRM_DISPLAY_MODE_LEN),
  ]

  def __repr__(self):
    return '<Mode %dx%d, vrefresh=%d>' % (
        self.hdisplay, self.vdisplay, self.vrefresh)

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeModeInfo(ctypes.byref(self))


class DRMModeConnector(DRMModeBaseStruct):
  """C struct of DRM mode connector.

  This is a Python representation of the following C struct in xf86drmMode.h:

    typedef enum {
            DRM_MODE_CONNECTED         = 1,
            DRM_MODE_DISCONNECTED      = 2,
            DRM_MODE_UNKNOWNCONNECTION = 3
    } drmModeConnection;

    typedef enum {
            DRM_MODE_SUBPIXEL_UNKNOWN        = 1,
            DRM_MODE_SUBPIXEL_HORIZONTAL_RGB = 2,
            DRM_MODE_SUBPIXEL_HORIZONTAL_BGR = 3,
            DRM_MODE_SUBPIXEL_VERTICAL_RGB   = 4,
            DRM_MODE_SUBPIXEL_VERTICAL_BGR   = 5,
            DRM_MODE_SUBPIXEL_NONE           = 6
    } drmModeSubPixel;

    typedef struct _drmModeConnector {
            uint32_t connector_id;
            uint32_t encoder_id; /**< Encoder currently connected to */
            uint32_t connector_type;
            uint32_t connector_type_id;
            drmModeConnection connection;
            uint32_t mmWidth, mmHeight; /**< HxW in millimeters */
            drmModeSubPixel subpixel;

            int count_modes;
            drmModeModeInfoPtr modes;

            int count_props;
            uint32_t *props; /**< List of property ids */
            uint64_t *prop_values; /**< List of property values */

            int count_encoders;
            uint32_t *encoders; /**< List of encoder ids */
    } drmModeConnector, *drmModeConnectorPtr;
  """
  # drmModeConnection
  DRM_MODE_CONNECTED = 1
  DRM_MODE_DISCONNECTED = 2
  DRM_MODE_UNKNOWNCONNECTION = 3

  # We use the same connector status names as in modetest.
  CONNECTOR_STATUS_NAMES = {
      DRM_MODE_CONNECTED: 'connected',
      DRM_MODE_DISCONNECTED: 'disconnected',
      DRM_MODE_UNKNOWNCONNECTION: 'unknown',
  }

  # drmModeSubPixel
  DRM_MODE_SUBPIXEL_UNKNOWN = 1
  DRM_MODE_SUBPIXEL_HORIZONTAL_RGB = 2
  DRM_MODE_SUBPIXEL_HORIZONTAL_BGR = 3
  DRM_MODE_SUBPIXEL_VERTICAL_RGB = 4
  DRM_MODE_SUBPIXEL_VERTICAL_BGR = 5
  DRM_MODE_SUBPIXEL_NONE = 6

  DRM_MODE_CONNECTOR_Unknown = 0
  DRM_MODE_CONNECTOR_VGA = 1
  DRM_MODE_CONNECTOR_DVII = 2
  DRM_MODE_CONNECTOR_DVID = 3
  DRM_MODE_CONNECTOR_DVIA = 4
  DRM_MODE_CONNECTOR_Composite = 5
  DRM_MODE_CONNECTOR_SVIDEO = 6
  DRM_MODE_CONNECTOR_LVDS = 7
  DRM_MODE_CONNECTOR_Component = 8
  DRM_MODE_CONNECTOR_9PinDIN = 9
  DRM_MODE_CONNECTOR_DisplayPort = 10
  DRM_MODE_CONNECTOR_HDMIA = 11
  DRM_MODE_CONNECTOR_HDMIB = 12
  DRM_MODE_CONNECTOR_TV = 13
  DRM_MODE_CONNECTOR_eDP = 14
  DRM_MODE_CONNECTOR_VIRTUAL = 15
  DRM_MODE_CONNECTOR_DSI = 16
  DRM_MODE_CONNECTOR_DPI = 17

  # We use the same connector names as in modetest.
  CONNECTOR_TYPE_NAMES = {
      DRM_MODE_CONNECTOR_Unknown: 'unknown',
      DRM_MODE_CONNECTOR_VGA: 'VGA',
      DRM_MODE_CONNECTOR_DVII: 'DVI-I',
      DRM_MODE_CONNECTOR_DVID: 'DVI-D',
      DRM_MODE_CONNECTOR_DVIA: 'DVI-A',
      DRM_MODE_CONNECTOR_Composite: 'composite',
      DRM_MODE_CONNECTOR_SVIDEO: 's-video',
      DRM_MODE_CONNECTOR_LVDS: 'LVDS',
      DRM_MODE_CONNECTOR_Component: 'component',
      DRM_MODE_CONNECTOR_9PinDIN: '9-pin DIN',
      DRM_MODE_CONNECTOR_DisplayPort: 'DP',
      DRM_MODE_CONNECTOR_HDMIA: 'HDMI-A',
      DRM_MODE_CONNECTOR_HDMIB: 'HDMI-B',
      DRM_MODE_CONNECTOR_TV: 'TV',
      DRM_MODE_CONNECTOR_eDP: 'eDP',
      DRM_MODE_CONNECTOR_VIRTUAL: 'Virtual',
      DRM_MODE_CONNECTOR_DSI: 'DSI',
      DRM_MODE_CONNECTOR_DPI: 'DPI',
  }

  _fields_ = [
      ('connector_id', ctypes.c_uint32),
      ('encoder_id', ctypes.c_uint32),
      ('connector_type', ctypes.c_uint32),
      ('connector_type_id', ctypes.c_uint32),
      ('connection', ctypes.c_uint),
      ('mmWidth', ctypes.c_uint32), ('mmHeight', ctypes.c_uint32),
      ('subpixel', ctypes.c_uint),
      ('count_modes', ctypes.c_int),
      ('modes', ctypes.POINTER(DRMModeModeInfo)),
      ('count_props', ctypes.c_int),
      ('props', ctypes.POINTER(ctypes.c_uint32)),
      ('prop_values', ctypes.POINTER(ctypes.c_uint64)),
      ('count_encoders', ctypes.c_int),
      ('encoders', ctypes.POINTER(ctypes.c_uint32)),
  ]

  def __repr__(self):
    return '<Connector %s, status=%s>' % (self.id, self.status)

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeConnector(ctypes.byref(self))

  @property
  def id(self):
    return '%s-%d' % (self.CONNECTOR_TYPE_NAMES[self.connector_type],
                      self.connector_type_id)

  @property
  def status(self):
    return self.CONNECTOR_STATUS_NAMES[self.connection]

  @property
  def encoder(self):
    encoder_ptr = _GetDRMLibrary().drmModeGetEncoder(self.fd, self.encoder_id)
    if encoder_ptr:
      encoder = encoder_ptr.contents
      encoder.fd = self.fd
      encoder.need_free = True
      return encoder
    return None

  @property
  def edid(self):
    blob_id = None
    for i in range(self.count_props):
      # 1 is the property id of "EDID" in Kernel Mode Setting (KMS):
      # https://www.kernel.org/doc/htmldocs/drm/drm-kms-properties.html
      if self.props[i] == 1:
        blob_id = self.prop_values[i]
    if not blob_id:
      return None

    blob = _GetDRMLibrary().drmModeGetPropertyBlob(self.fd, blob_id).contents
    blob.fd = self.fd
    blob.need_free = True
    return ctypes.cast(blob.data, ctypes.POINTER(ctypes.c_uint8))[0:blob.length]

  def GetAssociatedFramebuffer(self):
    """Gets the associate scanout buffer.

    Returns:
      A DRMModeFB instance.
    """
    if self.encoder:
      return self.encoder.crtc.framebuffer
    return None


class DRMModeEncoder(DRMModeBaseStruct):
  """C struct of DRM mode encoder.

  This is a Python representation of the following C struct in xf86drmMode.h:

    typedef struct _drmModeEncoder {
            uint32_t encoder_id;
            uint32_t encoder_type;
            uint32_t crtc_id;
            uint32_t possible_crtcs;
            uint32_t possible_clones;
    } drmModeEncoder, *drmModeEncoderPtr;
  """
  _fields_ = [
      ('encoder_id', ctypes.c_uint32),
      ('encoder_type', ctypes.c_uint32),
      ('crtc_id', ctypes.c_uint32),
      ('possible_crtcs', ctypes.c_uint32),
      ('possible_clones', ctypes.c_uint32),
  ]

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeEncoder(ctypes.byref(self))

  @property
  def crtc(self):
    crtc = _GetDRMLibrary().drmModeGetCrtc(self.fd, self.crtc_id).contents
    crtc.fd = self.fd
    crtc.need_free = True
    return crtc


class DRMModeCrtc(DRMModeBaseStruct):
  """C struct of DRM mode CRTC.

  This is a Python representation of the following C struct in xf86drmMode.h:

    typedef struct _drmModeCrtc {
            uint32_t crtc_id;
            uint32_t buffer_id; /**< FB id to connect to 0 = disconnect */

            uint32_t x, y; /**< Position on the framebuffer */
            uint32_t width, height;
            int mode_valid;
            drmModeModeInfo mode;

            int gamma_size; /**< Number of gamma stops */
    } drmModeCrtc, *drmModeCrtcPtr;
  """
  _fields_ = [
      ('crtc_id', ctypes.c_uint32),
      ('buffer_id', ctypes.c_uint32),
      ('x', ctypes.c_uint32), ('y', ctypes.c_uint32),
      ('width', ctypes.c_uint32), ('height', ctypes.c_uint32),
      ('mode_valid', ctypes.c_int),
      ('mode', DRMModeModeInfo),
      ('gamma_size', ctypes.c_int),
  ]

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeCrtc(ctypes.byref(self))

  @property
  def framebuffer(self):
    if not self.buffer_id:
      return None
    ret = _GetDRMLibrary().drmModeGetFB(self.fd, self.buffer_id).contents
    ret.fd = self.fd
    ret.need_free = True
    return ret


class DRMModeFB(DRMModeBaseStruct):
  """C struct of DRM mode framebuffer.

  This is a Python representation of the following C struct xf86drmMode.h:

    typedef struct _drmModeFB {
            uint32_t fb_id;
            uint32_t width, height;
            uint32_t pitch;
            uint32_t bpp;
            uint32_t depth;
            /* driver specific handle */
            uint32_t handle;
    } drmModeFB, *drmModeFBPtr;
  """
  _fields_ = [
      ('fb_id', ctypes.c_uint32),
      ('width', ctypes.c_uint32), ('height', ctypes.c_uint32),
      ('pitch', ctypes.c_uint32),
      ('bpp', ctypes.c_uint32),
      ('depth', ctypes.c_uint32),
      ('handle', ctypes.c_uint32),
  ]
  _map = None

  # The ioctl number here is pre-computed. It can't be imported from libdrm
  # since the constant is a #define in the C source code.
  DRM_IOCTL_MODE_MAP_DUMB = 0xc01064b3

  class DRMModeMapDumb(ctypes.Structure):
    """/* set up for mmap of a dumb scanout buffer */ struct drm_mode_map_dumb {

            /** Handle for the object being mapped. */
            __u32 handle;
            __u32 pad;
            /**
             * Fake offset to use for subsequent mmap call
             *
             * This is a fixed-size type for 32/64 compatibility.
             */
            __u64 offset;
    };
    """
    _fields_ = [
        ('handle', ctypes.c_uint32),
        ('pad', ctypes.c_uint32),
        ('offset', ctypes.c_uint64),
    ]

  def __repr__(self):
    return '<Framebuffer %dx%d, pitch=%d, bpp=%d, depth=%d>' % (
        self.width, self.height, self.pitch, self.bpp, self.depth)

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreeFB(ctypes.byref(self))

  @property
  def contents(self):
    try:
      self.map()
      size = self.pitch * self.height
      return self._map.read(size)
    finally:
      self.unmap()

  def AsRGBImage(self):
    """Converts the contents of the framebuffer to a RGB Image() instance.

    Returns:
      A Image() instance with mode='RGB' of the converted framebuffer.
    """
    if self.depth != 24:
      raise DRMError('Unable to convert depth %s' % self.depth)

    return Image.fromstring(
        'RGB', (self.width, self.height), self.contents, 'raw', 'BGRX')

  def map(self):
    if self._map:
      return
    map_dumb = self.DRMModeMapDumb()
    # pylint: disable=attribute-defined-outside-init
    map_dumb.handle = self.handle
    ret = _GetDRMLibrary().drmIoctl(self.fd, self.DRM_IOCTL_MODE_MAP_DUMB,
                                    ctypes.byref(map_dumb))
    if ret:
      raise DRMError(ret, os.strerror(ret))
    size = self.pitch * self.height
    self._map = mmap.mmap(self.fd, size, flags=mmap.MAP_SHARED,
                          prot=mmap.PROT_READ, offset=map_dumb.offset)

  def unmap(self):
    if self._map:
      self._map.close()
      self._map = None


class DRMModePropertyBlob(DRMModeBaseStruct):
  """C struct of DRM mode property blob.

  This is a Python representation of the following C struct xf86drmMode.h:

    typedef struct _drmModePropertyBlob {
            uint32_t id;
            uint32_t length;
            void *data;
    } drmModePropertyBlobRes, *drmModePropertyBlobPtr;
  """
  _fields_ = [
      ('id', ctypes.c_uint32),
      ('length', ctypes.c_uint32),
      ('data', ctypes.c_void_p),
  ]

  def __del__(self):
    if self.need_free:
      _GetDRMLibrary().drmModeFreePropertyBlob(ctypes.byref(self))


class DRM:
  """An abstraction of the DRM device."""

  def __init__(self, handle):
    self.handle = handle
    self.fd = handle.fileno()

  @property
  def resources(self):
    resources_ptr = _GetDRMLibrary().drmModeGetResources(self.fd)
    if resources_ptr and resources_ptr.contents.count_connectors:
      ret = resources_ptr.contents
      ret.fd = self.fd
      ret.need_free = True
      return ret
    return None


def DRMFromPath(path):
  """Opens the DRM device from path.

  Args:
    path: the path of minor node.

  Returns:
    A DRM instance.
  """
  return DRM(open(path))


def _LoadDRMLibrary():
  """Loads the userland DRM library."""
  lib = ctypes.cdll.LoadLibrary('libdrm.so')

  lib.drmModeGetResources.argtypes = [ctypes.c_int]
  lib.drmModeGetResources.restype = ctypes.POINTER(DRMModeResource)
  lib.drmModeFreeResources.argtypes = [ctypes.POINTER(DRMModeResource)]
  lib.drmModeFreeResources.restype = None

  lib.drmModeGetConnector.argtypes = [ctypes.c_int, ctypes.c_uint32]
  lib.drmModeGetConnector.restype = ctypes.POINTER(DRMModeConnector)
  lib.drmModeFreeConnector.argtypes = [ctypes.POINTER(DRMModeConnector)]
  lib.drmModeFreeConnector.restype = None

  lib.drmModeGetEncoder.argtypes = [ctypes.c_int, ctypes.c_uint32]
  lib.drmModeGetEncoder.restype = ctypes.POINTER(DRMModeEncoder)
  lib.drmModeFreeEncoder.argtypes = [ctypes.POINTER(DRMModeEncoder)]
  lib.drmModeFreeEncoder.restype = None

  lib.drmModeGetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32]
  lib.drmModeGetCrtc.restype = ctypes.POINTER(DRMModeCrtc)
  lib.drmModeFreeCrtc.argtypes = [ctypes.POINTER(DRMModeCrtc)]
  lib.drmModeFreeCrtc.restype = None

  lib.drmModeGetFB.argtypes = [ctypes.c_int, ctypes.c_uint32]
  lib.drmModeGetFB.restype = ctypes.POINTER(DRMModeFB)
  lib.drmModeFreeFB.argtypes = [ctypes.POINTER(DRMModeFB)]
  lib.drmModeFreeFB.restype = None

  lib.drmModeGetPropertyBlob.argtypes = [ctypes.c_int, ctypes.c_uint32]
  lib.drmModeGetPropertyBlob.restype = ctypes.POINTER(DRMModePropertyBlob)
  lib.drmModeFreePropertyBlob.argtypes = [ctypes.POINTER(DRMModePropertyBlob)]
  lib.drmModeFreePropertyBlob.restype = None

  lib.drmIoctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_voidp]
  lib.drmIoctl.restype = ctypes.c_int

  lib.drmSetMaster.argtypes = [ctypes.c_int]
  lib.drmSetMaster.restypes = ctypes.c_int
  lib.drmDropMaster.argtypes = [ctypes.c_int]
  lib.drmDropMaster.restypes = ctypes.c_int

  lib.drmModeConnectorSetProperty.argtypes = [ctypes.c_int, ctypes.c_uint32,
                                              ctypes.c_uint32, ctypes.c_uint64]
  lib.drmModeConnectorSetProperty.restype = ctypes.c_int

  return lib


def _GetDRMLibrary():
  if _lib:
    return _lib
  raise DRMError('DRM library is not available')


try:
  _lib = _LoadDRMLibrary()
except OSError:
  _lib = None
