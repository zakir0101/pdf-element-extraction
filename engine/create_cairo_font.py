import ctypes as ct
from math import isnan
import cairo
import freetype
import os
from .pdf_utils import open_image_in_irfan, kill_with_taskkill
import pprint
from fontTools.agl import UV2AGL
import sys
import subprocess


SEP = os.path.sep

_initialized = False

if os.name == "nt":  # Windows
    _freetype_so = ct.CDLL(f"D:{SEP}Software{SEP}cairo{SEP}freetype.dll")
    _cairo_so = ct.CDLL(f"D:{SEP}Software{SEP}cairo{SEP}cairo.dll")
else:  # Unix-like
    _freetype_so = ct.CDLL("libfreetype.so.6")
    _cairo_so = ct.CDLL("libcairo.so.2")


class PycairoContext(ct.Structure):
    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("ctx", ct.c_void_p),
        ("base", ct.c_void_p),
    ]


def create_cairo_font_face_for_file(
    filename,
    faceindex=0,
    loadoptions=0,
    encoding=None,
    # encoding=ADBC
):
    "given the name of a font file, and optional faceindex to pass to FT_New_Face" " and loadoptions to pass to cairo_ft_font_face_create_for_ft_face, creates" " a cairo.FontFace object that may be used to render text with that font."
    global _initialized
    global _freetype_so
    global _cairo_so
    global _ft_lib
    global _ft_destroy_key
    global _surface

    CAIRO_STATUS_SUCCESS = 0
    FT_Err_Ok = 0
    cairo_ctx = None
    if not _initialized:

        _cairo_so.cairo_ft_font_face_create_for_ft_face.restype = ct.c_void_p
        _cairo_so.cairo_ft_font_face_create_for_ft_face.argtypes = [
            ct.c_void_p,
            ct.c_int,
        ]
        _cairo_so.cairo_font_face_get_user_data.restype = ct.c_void_p
        _cairo_so.cairo_font_face_get_user_data.argtypes = (
            ct.c_void_p,
            ct.c_void_p,
        )
        _cairo_so.cairo_font_face_set_user_data.argtypes = (
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
        )
        _cairo_so.cairo_set_font_face.argtypes = [ct.c_void_p, ct.c_void_p]
        _cairo_so.cairo_font_face_status.argtypes = [ct.c_void_p]
        _cairo_so.cairo_font_face_destroy.argtypes = (ct.c_void_p,)
        _cairo_so.cairo_status.argtypes = [ct.c_void_p]

        _cairo_so.cairo_ft_scaled_font_lock_face.restype = ct.c_void_p
        _cairo_so.cairo_ft_scaled_font_lock_face.argtypes = [ct.c_void_p]
        _cairo_so.cairo_ft_scaled_font_unlock_face.argtypes = [ct.c_void_p]
        # initialize freetype
        _ft_lib = ct.c_void_p()
        status = _freetype_so.FT_Init_FreeType(ct.byref(_ft_lib))
        if status != FT_Err_Ok:
            raise RuntimeError(
                "Error %d initializing FreeType library." % status
            )

        _surface = cairo.ImageSurface(cairo.FORMAT_A8, 0, 0)
        _ft_destroy_key = ct.c_int()  # dummy address
        _initialized = True

    ft_face = ct.c_void_p()
    cr_face = None
    try:
        status = _freetype_so.FT_New_Face(
            _ft_lib, filename.encode("utf-8"), faceindex, ct.byref(ft_face)
        )

        if status != FT_Err_Ok:
            raise RuntimeError(
                "Error %d creating FreeType font face for %s"
                % (status, filename)
            )

        if encoding != None:
            status = _freetype_so.FT_Select_Charmap(ft_face, encoding)
            if status != FT_Err_Ok:
                # if _freetype_so.FT_Get_Face_Flags(ft_face) & (1 << 16):
                #     pass
                # else:
                raise RuntimeError("Font has no Unicode charmap")
        cr_face = _cairo_so.cairo_ft_font_face_create_for_ft_face(
            ft_face, loadoptions
        )
        status = _cairo_so.cairo_font_face_status(cr_face)
        if status != CAIRO_STATUS_SUCCESS:
            raise RuntimeError(
                "Error %d creating cairo font face for %s" % (status, filename)
            )

        # ++++++++++++++ unnecessary ++++++++++++++++++++++++++++++
        if (
            _cairo_so.cairo_font_face_get_user_data(
                cr_face, ct.byref(_ft_destroy_key)
            )
            == None
        ):
            status = _cairo_so.cairo_font_face_set_user_data(
                cr_face,
                ct.byref(_ft_destroy_key),
                ft_face,
                _freetype_so.FT_Done_Face,
            )
            if status != CAIRO_STATUS_SUCCESS:
                raise RuntimeError(
                    "Error %d doing user_data dance for %s"
                    % (status, filename)
                )
            ft_face = None  # Cairo has stolen my reference

        cairo_ctx = cairo.Context(_surface)
        cairo_t = PycairoContext.from_address(id(cairo_ctx)).ctx
        _cairo_so.cairo_set_font_face(cairo_t, cr_face)
        status = _cairo_so.cairo_font_face_status(cairo_t)
        if status != CAIRO_STATUS_SUCCESS:
            raise RuntimeError(
                "Error %d creating cairo font face for %s" % (status, filename)
            )
    except Exception as e:
        print(f"Error while Trying to lead font: {filename}")
        print(e)
        raise Exception(e)
    finally:
        _cairo_so.cairo_font_face_destroy(cr_face)
        _freetype_so.FT_Done_Face(ft_face)

    if cairo_ctx is None:
        return None
    face = cairo_ctx.get_font_face()
    return face
