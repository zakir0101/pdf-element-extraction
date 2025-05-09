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


if os.name == "nt":  # Windows
    ansi = "ansi"
else:
    ansi = "iso_8859_1"


SEP = os.path.sep
_initialized = False

if os.name == "nt":  # Windows
    _freetype_so = ct.CDLL(f"D:{SEP}Software{SEP}cairo{SEP}freetype.dll")
    _cairo_so = ct.CDLL(f"D:{SEP}Software{SEP}cairo{SEP}cairo.dll")
else:  # Unix-like
    _freetype_so = ct.CDLL("libfreetype.so.6")
    _cairo_so = ct.CDLL("libcairo.so.2")

ROM = freetype.FT_ENCODINGS.get("FT_ENCODING_APPLE_ROMAN")
MSE = freetype.FT_ENCODINGS.get("FT_ENCODING_MS_SYMBOL")
UNIC = freetype.FT_ENCODINGS.get("FT_ENCODING_UNICODE")
ADBC = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_CUSTOM")
ADBS = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_STANDARD")
ADBE = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_EXPERT")
ADBL = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_LATIN1")

# CURR_ENCODING = ADBC

ENC_LIST = [ADBC, ADBE, ADBS, ADBL, UNIC]


class PycairoFontFace(ct.Structure):
    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("font_face", ct.c_void_p),
        ("base", ct.c_void_p),
    ]


class PycairoContext(ct.Structure):
    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("ctx", ct.c_void_p),
        ("base", ct.c_void_p),
    ]


class PycairoScaledFont(ct.Structure):

    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("scaled_font", ct.c_void_p),
    ]


def cairo_lock_ft_face(scaled_font):
    """
    Return (ft_face_ptr, unlock_func) where:
        ft_face_ptr – a ctypes.c_void_p,  *exactly* the face Cairo draws with
        unlock_func – call this when you’re done (mirrors Cairo’s API)
    """

    _cairo = _cairo_so  # already loaded in your script
    _cairo.cairo_ft_scaled_font_unlock_face.argtypes = [ct.c_void_p]
    # return ct.c_void_p(
    #     ft_face
    # ), lambda: _cairo.cairo_ft_scaled_font_unlock_face(sfont_ptr)


def build_gid_map_from_cairo(ctx, ft_face_ptr, unlock):
    """
    Return two dicts based on the **FT_Face that Cairo is using**:

        name → cairo_gid
        cmap_gid(platform 7/2) → cairo_gid   (if that cmap exists)

    Works for any font; if no 7/2 cmap, the second dict is empty.
    """
    try:
        face_cairo = freetype.Face.__new__(freetype.Face)
        face_cairo._FT_Face = ft_face_ptr  # ⚠ private attribute

        name_to_gid = {
            face_cairo.get_glyph_name(g).decode("ascii", "replace"): g
            for g in range(face_cairo.num_glyphs)
        }

        # 2) if the font has platform-7/encoding-2, make cmap→gid map
        cmap_gid_to_cairo = {}
        for cmap in face_cairo.charmaps:
            if cmap.platform_id == 7 and cmap.encoding_id == 2:
                face_cairo.set_charmap(cmap)
                for _, gid in face_cairo.get_chars():
                    gname = face_cairo.get_glyph_name(gid).decode(
                        "ascii", "replace"
                    )
                    cmap_gid_to_cairo[gid] = name_to_gid.get(gname, 0)
                break

        return name_to_gid, cmap_gid_to_cairo

    finally:
        unlock()  # always unlock the face


def create_cairo_font_face_for_file(
    filename, faceindex=0, loadoptions=0, encoding=ADBC
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
        print(e)
    finally:
        _cairo_so.cairo_font_face_destroy(cr_face)
        _freetype_so.FT_Done_Face(ft_face)

    if cairo_ctx is None:
        return None
    face = cairo_ctx.get_font_face()
    return face


def old_test():

    face = create_cairo_font_face_for_file(
        # f "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        r"D:\Software\Fonts\0xProto\0xProtoNerdFont-Bold.ttf",
        0,
    )
    if face is None:
        exit(1)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 128, 128)
    ctx = cairo.Context(surface)

    ctx.set_font_face(face)
    ctx.set_font_size(30)
    ctx.move_to(0, 44)
    ctx.show_text("Hello,")
    ctx.move_to(30, 74)
    ctx.show_text("world!")

    del ctx

    surface.write_to_png("output\\hello.png")


# ------------------------------------------------------------
# 1.  Debug helper – print the mapping table
# ------------------------------------------------------------
def dump_glyph_table(font_path, start, limit=None):
    """
    Print Unicode-to-glyph mapping for *font_path* without ever calling Cairo.
    Columns:
        cp         – Unicode code-point (hex)
        chr        – printable character (or '?')
        raw_gid    – glyph ID returned by the active char-map
        gname      – PostScript glyph name stored in that slot
    """
    import freetype, os, textwrap

    face = freetype.Face(font_path)

    is_composite = len(face.charmaps) == 0
    # face.select__charmap(CURR_ENCODING)
    print("_is_cid_keyed", is_composite)
    if not is_composite:
        for enc in ENC_LIST:
            try:
                face.select_charmap(enc)
                break
            except Exception as e:
                print(f"Error setting font {font_path} to enc: {enc}")

        if enc is None:
            face.set_charmap(face.charmaps[0])
            enc = face.charmap.encoding

        cm = face.charmap
    else:
        enc = None

    font_size = 40
    width = 2000
    height = font_size * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()  # white bg

    toy_font = ctx.get_scaled_font()
    face_cairo = create_cairo_font_face_for_file(font_path, 0, encoding=enc)
    print("'imported' font_face = ", face_cairo)
    print("default font face =    ", toy_font)
    ctx.set_font_face(face_cairo)

    print("charmaps count is = ", len(face.charmaps))

    print("number of glyphs = ", face.num_glyphs)
    # print("\n" + "-" * 60)
    print(f"Font    : {os.path.basename(font_path)}")
    # print(f"Charmap : platform {cm.platform_id}, encoding {cm.encoding_id}")
    print("ch_c  chr  raw_gid    glyph_name")
    print("----  ---- -------    ----------")

    # name_to_cairo_gid = {
    #     face.get_glyph_name(g).decode("ascii", "replace"): g
    #     for g in range(face.num_glyphs)
    # }
    count = 0
    gnames = []
    cp, raw_gid = face.get_first_char()
    while gnames == [] or raw_gid != 0:
        # for cp, raw_gid in face._get_glyph():
        if limit and count >= limit:
            break
        char = chr(cp)  # if 32 <= cp < 0x7F else "?"

        if face._has_glyph_names():
            try:
                gname = face.get_glyph_name(raw_gid)
            except Exception:
                gname = "<none>"
        else:
            gname = UV2AGL.get(cp) or "<unavailable>"

        gnames.append(raw_gid)
        name_index = ""  # face.get_name_index(gname)
        print(f"{cp:3}  {char:>3}   {raw_gid:8}   {gname:10}  ")
        count += 1
        cp, raw_gid = face.get_next_char(cp, raw_gid)

    return gnames


# ------------------------------------------------------------
# 2.
# ------------------------------------------------------------
def get_first_n_glyphs(face: freetype.Face, is_composite):

    pen_x, glyphs = 0, []
    y = 30
    counter = 0
    if not is_composite:
        ch, gid = face.get_first_char()
        while len(glyphs) == 0 or gid != 0:
            if counter % 12 == 0:
                y = y + 50
                pen_x = 0
            if not isnan(gid) and not is_composite:
                glyphs.append(cairo.Glyph(gid, pen_x, y))
            else:

                glyphs.append(cairo.Glyph(ch, pen_x, y))
            pen_x += 30
            ch, gid = face.get_next_char(ch, gid)
            counter += 1
        return glyphs
    else:
        for i in range(1, 60):
            if counter % 12 == 0:
                y = y + 50
                pen_x = 0
            print(chr(i))
            glyphs.append(cairo.Glyph(i, pen_x, y))
            pen_x += 30
            counter += 1
        return glyphs


# ------------------------------------------------------------
# 3.  Draw the first N printable glyphs to a PNG
# ------------------------------------------------------------


def draw_first_n_glyphs(font_path, gids, out_png="glyphs.png"):
    face_ft = freetype.Face(font_path)

    # face_ft.select_charmap(CURR_ENCODING)
    print("number of charmap is : ", len(face_ft.charmaps))
    is_composite = len(face_ft.charmaps) == 0
    if not is_composite:
        for enc in ENC_LIST:
            try:
                face_ft.select_charmap(enc)
                break
            except Exception as e:
                pass
                # print(f"Error setting font {font_path} to enc: {enc}")

        if enc is None:
            face_ft.set_charmap(face_ft.charmaps[0])
            enc = face_ft.charmap.encoding
    else:
        enc = None
    font_size = 20
    glyphs = get_first_n_glyphs(face_ft, is_composite)
    face_cairo = create_cairo_font_face_for_file(font_path, 0, encoding=enc)
    width = 500
    height = 500

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()  # white bg
    ctx.set_font_size(font_size)
    ctx.set_font_face(face_cairo)
    ctx.set_source_rgb(0, 0, 0)  # black text

    ctx.show_glyphs(glyphs)
    surface.write_to_png(out_png)

    # print(f"Wrote {out_png}")
    open_image_in_irfan(out_png)


def in_wsl() -> bool:
    """True if running under Windows Subsystem for Linux."""
    return os.name == "posix" and (
        "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ
    )


if __name__ == "__main__":
    kill_with_taskkill()
    for f in os.listdir("temp"):
        if not f.startswith("T1_2"):
            continue
        # FONT_PATH = r"D:\Software\Fonts\0xProto\0xProtoNerdFont-Bold.ttf"
        FONT_TYPE1 = f"temp" + SEP + f
        FONT_PATH = FONT_TYPE1
        FONT_SIZE = 30
        LINE_HEIGHT = 30

        start = int(f.split(".")[0].split("_")[-1])
        gids = dump_glyph_table(FONT_PATH, 0)
        draw_first_n_glyphs(
            FONT_PATH,
            [],
            "output" + SEP + f"glyphs_{f.split('.')[0]}.png",
        )

    # kill_with_taskkill()
