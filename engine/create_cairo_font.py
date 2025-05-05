
import ctypes as ct, cairo, freetype
import os
import pprint
from traceback import print_stack
from fontTools.agl import UV2AGL
from freetype import FT_ENCODINGS, raw

_initialized = False

if os.name == "nt":  # Windows
    _freetype_so = ct.CDLL("D:\\Software\\cairo\\freetype.dll")
    _cairo_so = ct.CDLL("D:\\Software\\cairo\\cairo.dll")
    # _cairo_so = ct.CDLL(r".\venv\Lib\site-packages\cairo\_cairo.cp312-win_amd64.pyd")
    # cairo.__loader__
else:  # Unix-like
    _freetype_so = ct.CDLL("libfreetype.so.6")
    _cairo_so = ct.CDLL("libcairo.so.2")

LAT1 = freetype.FT_ENCODINGS.get('FT_ENCODING_ADOBE_LATIN1')
UNIC = freetype.FT_ENCODINGS.get('FT_ENCODING_UNICODE')
ADB = freetype.FT_ENCODINGS.get('FT_ENCODING_ADOBE_STANDARD')
ROM = freetype.FT_ENCODINGS.get('FT_ENCODING_APPLE_ROMAN')
MSE = freetype.FT_ENCODINGS.get('FT_ENCODING_MS_SYMBOL')
ADBC =freetype.FT_ENCODINGS.get('FT_ENCODING_ADOBE_CUSTOM')

CURR_ENCODING = UNIC 
# In create_cairo_font.py around line 62
class PycairoFontFace(ct.Structure):
    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("font_face", ct.c_void_p),
        ("base", ct.c_void_p),
    ]

class PycairoContext(ct.Structure):
    # Add safety check for object.__basicsize__
    # if hasattr(object, "__basicsize__"):
    _fields_ = [
        ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        ("ctx", ct.c_void_p),
        ("base", ct.c_void_p),
    ]
    # else:
    #     _fields_ = [
    #         ("PyObject_HEAD", ct.c_byte * 16),  # Reasonable default
    #         ("ctx", ct.c_void_p),
    #         ("base", ct.c_void_p),
    #     ]

    # @classmethod
    # def from_address(cls, address):
    #     try:
    #         return super(PycairoContext, cls).from_address(address)
    #     except Exception:
    #         # Return a dummy context to prevent crash
    #         print("Error: Unable to create PycairoContext from address.")
    #         dummy = cls()
    #         dummy.ctx = None
    #         dummy.base = None
    #         return dummy


# ------------------------------------------------------------------
# grab the C pointer inside a Pycairo ScaledFont object
class PycairoScaledFont(ct.Structure):

    if hasattr(object, "__basicsize__"):
        _fields_ = [("PyObject_HEAD", ct.c_byte * object.__basicsize__),
                    ("scaled_font", ct.c_void_p)]
    else:
        _fields_ = [("PyObject_HEAD", ct.c_byte * 16),
                    ("scaled_font", ct.c_void_p)]

    @classmethod
    def from_address(cls, address):
        try:
            return super(PycairoContext, cls).from_address(address)
        except Exception:
            # Return a dummy context to prevent crash
            dummy = cls()
            dummy.ctx = None
            dummy.base = None
            return dummy

def cairo_lock_ft_face(scaled_font):
    """
    Return (ft_face_ptr, unlock_func) where:
        ft_face_ptr – a ctypes.c_void_p,  *exactly* the face Cairo draws with
        unlock_func – call this when you’re done (mirrors Cairo’s API)
    """
    _cairo = _cairo_so                         # already loaded in your script
    _cairo.cairo_ft_scaled_font_unlock_face.argtypes = [ct.c_void_p]
    return ct.c_void_p(ft_face), lambda: _cairo.cairo_ft_scaled_font_unlock_face(sfont_ptr)

    
def build_gid_map_from_cairo(ctx, ft_face_ptr, unlock):
    """
    Return two dicts based on the **FT_Face that Cairo is using**:

        name → cairo_gid
        cmap_gid(platform 7/2) → cairo_gid   (if that cmap exists)

    Works for any font; if no 7/2 cmap, the second dict is empty.
    """
    # --- lock Cairo's FT_Face ----------------------------------------
    # ft_face_ptr, unlock = cairo_lock_ft_face(ctx.get_scaled_font())
    try:
        # wrap the raw pointer with freetype-py, zero-copy
        face_cairo = freetype.Face.__new__(freetype.Face)
        face_cairo._FT_Face = ft_face_ptr       # ⚠ private attribute

        # 1) glyph-name → cairo-gid
        name_to_gid = {
            face_cairo.get_glyph_name(g).decode('ascii', 'replace'): g
            for g in range(face_cairo.num_glyphs)
        }

        # 2) if the font has platform-7/encoding-2, make cmap→gid map
        cmap_gid_to_cairo = {}
        for cmap in face_cairo.charmaps:
            if cmap.platform_id == 7 and cmap.encoding_id == 2:
                face_cairo.set_charmap(cmap)
                for _, gid in face_cairo.get_chars():
                    gname = face_cairo.get_glyph_name(gid).decode('ascii','replace')
                    cmap_gid_to_cairo[gid] = name_to_gid.get(gname, 0)
                break

        return name_to_gid, cmap_gid_to_cairo

    finally:
        unlock()          # always unlock the face



def create_cairo_font_face_for_file(filename, faceindex=0, loadoptions=0):
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
        # find shared objects

        # _freetype_so = ct.CDLL("libfreetype.so.6")
        # _cairo_so = ct.CDLL("libcairo.so.2")


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
        # end if

        # class PycairoContext(ct.Structure):
        #     _fields_ = [
        #         ("PyObject_HEAD", ct.c_byte * object.__basicsize__),
        #         ("ctx", ct.c_void_p),
        #         ("base", ct.c_void_p),
        #     ]

        # end PycairoContext

        _surface = cairo.ImageSurface(cairo.FORMAT_A8, 0, 0)
        _ft_destroy_key = ct.c_int()  # dummy address
        _initialized = True
    # end if

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
        # end if

        # --- ★ 1.  pick the cmap you want ------------------------------------
        # (or use 0x00005043 for SYMBOL etc.; full list in FT docs)

        status = _freetype_so.FT_Select_Charmap(ft_face
                                                ,CURR_ENCODING 
                                                )
        if status != FT_Err_Ok:
            raise RuntimeError("Font has no Unicode charmap")

        # --------------------------------------------------------------------
        # create Cairo font face for freetype face
        cr_face = _cairo_so.cairo_ft_font_face_create_for_ft_face(
            ft_face, loadoptions
        )
        status = _cairo_so.cairo_font_face_status(cr_face)
        if status != CAIRO_STATUS_SUCCESS:
            raise RuntimeError(
                "Error %d creating cairo font face for %s" % (status, filename)
            )



        # ++++++++++++++ unnecessary ++++++++++++++++++++++++++++++
        # if (
        #     _cairo_so.cairo_font_face_get_user_data(
        #         cr_face, ct.byref(_ft_destroy_key)
        #     )
        #     == None
        # ):
        #     status = _cairo_so.cairo_font_face_set_user_data(
        #         cr_face,
        #         ct.byref(_ft_destroy_key),
        #         ft_face,
        #         _freetype_so.FT_Done_Face,
        #     )
        #     if status != CAIRO_STATUS_SUCCESS:
        #         raise RuntimeError(
        #             "Error %d doing user_data dance for %s"
        #             % (status, filename)
        #         )
        #     ft_face = None  # Cairo has stolen my reference


        # return PycairoFontFace.from_address(cr_face).font_face
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

    if  cairo_ctx is None:
        return None
    face = cairo_ctx.get_font_face()
    return face


# end create_cairo_font_face_for_file

def old_test():

    face = create_cairo_font_face_for_file(
        # f "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        r"D:\Software\Fonts\0xProto\0xProtoNerdFont-Bold.ttf",
         0
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

def _activate_unicode_charmap(face: freetype.Face):
    """Select a Unicode charmap on *face* (platform 0 or 3 & enc 1 or 10)."""
    for cmap in face.charmaps:                        # iterate available maps
        pid, eid = cmap.platform_id, cmap.encoding_id
        if pid == 0 or (pid == 3 and eid in (1, 10)): # Unicode BMP / full
            face.set_charmap(cmap)                    # <── the reliable call
            return
    raise RuntimeError("No Unicode charmap found in font")


def main_text():

    # ------------------------------------------------------------------
    face = create_cairo_font_face_for_file(FONT_PATH, 0)
    if face is None:
        raise SystemExit("Couldn’t create Cairo font face")

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 256, 128)
    ctx     = cairo.Context(surface)

    # white background
    ctx.set_source_rgb(1, 1, 1); ctx.paint()

    ctx.set_font_face(face)
    ctx.set_font_size(FONT_SIZE)
    ctx.set_source_rgb(0, 0, 0)        # black text

    glyphs_1 = text_to_glyphs("Hello,", FONT_PATH, FONT_SIZE, 0,  44)
    glyphs_2 = text_to_glyphs("world!", FONT_PATH, FONT_SIZE, 30, 44+LINE_HEIGHT)

    ctx.show_glyphs(glyphs_1)
    ctx.show_glyphs(glyphs_2)

    surface.write_to_png(r"output\hello.png")

# ------------------------------------------------------------
# 1.  Choose a Unicode charmap if the font has one
# ------------------------------------------------------------
def _activate_best_charmap(face):
    """Return True if a Unicode charmap (platform 0 or 3/1|10) was activated,
    otherwise leave the current charmap in place (often 3/0 = MS-Symbol)
    and return False."""
    for cmap in face.charmaps:
        pid, eid = cmap.platform_id, cmap.encoding_id
        if pid == 0 or (pid == 3 and eid in (1, 10)):
            face.set_charmap(cmap)
            return True
    return False          

# ------------------------------------------------------------
# 3.  Debug helper – print the mapping table
# ------------------------------------------------------------
def dump_glyph_table(font_path,start, limit=None):
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

    #  freetype._FT_ENC_TAG( 'l','a','t','1' )

    chosen = None
    for cmap in face.charmaps:
        print("iterating cmpas",cmap.platform_id, cmap.encoding)
        # if cmap.encoding == LAT1:                      # 1️⃣ WinAnsi found
        #     chosen = cmap
        #     break
    #
    # if chosen is None:
    #     for cmap in face.charmaps:
    #         pid, eid = cmap.platform_id, cmap.encoding_id
    #         if pid == 0 or (pid == 3 and eid in (1, 10)):   # 2️⃣ Unicode BMP/full
    #             chosen = cmap
    #             break
    



    # for key,value in freetype.FT_ENCODINGS.items():
    #     print(key,value)

    # print("LAT1 encoding is ", LAT1)
    # print("UNICODE encoding is ", UNIC)

    face.select_charmap(CURR_ENCODING) 
    cm = face.charmap

    font_size = 40
    width = 2000
    height = font_size * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1); ctx.paint()     # white bg

    face_cairo = create_cairo_font_face_for_file(font_path, 0)
    print("'imported' font_face = " ,face_cairo)
    print("default font face =    ",ctx.get_font_face())
    ctx.set_font_face(face_cairo)



    print("charmaps count is = ", len(face.charmaps))
    print("\n" + "-" * 60)
    print(f"Font    : {os.path.basename(font_path)}")
    # print(f"Charmap : platform {cm.platform_id}, encoding {cm.encoding_id}")
    print("ch_c  chr  raw_gid  glyph_name    actual_glyph ")
    print("----  ---- -------  ----------    ------------ ")

    name_to_cairo_gid = {
        face.get_glyph_name(g).decode("ascii", "replace"): g
        for g in range(face.num_glyphs)
    }
    count = 0
    gnames = []

    cp , raw_gid  = face.get_first_char()
    # for cp, raw_gid in face.get_chars():                # iterate the cmap
    while gnames == [] or raw_gid != 0:
        if limit and count >= limit:
            break
        char = chr(cp) # if 32 <= cp < 0x7F else "?"

        act_glyph_id = ctx.get_scaled_font().text_to_glyphs(0,30,char,False)[0][0]
        try:
            gname = face.get_glyph_name(raw_gid).decode("ascii", "replace")
        except Exception:
            gname = "<none>"
        gnames.append(raw_gid)
        name_index = "" # face.get_name_index(gname)
        print(f"{cp:4}  {char:>4}   {raw_gid:8}   {gname:8}  {act_glyph_id:9} ")
        count += 1
        cp, raw_gid = face.get_next_char(cp, raw_gid)

    return gnames
# ------------------------------------------------------------
# 2.  Convert a text string to (gid,x,y) tuples for show_glyphs
# ------------------------------------------------------------
def text_to_glyphs(text, face, font_size, x0=0, y0=0):
    """Return Cairo glyph tuples, doing the MS-Symbol (gid-1) correction
    **only when** we are stuck on charmap 3/0."""
    unicode_ok = _activate_best_charmap(face)
    is_ms_symbol = not unicode_ok and \
                   face.charmap.platform_id == 3 and face.charmap.encoding_id == 0

    face.set_char_size(int(font_size * 64))      # 26.6 fixed-point

    pen_x, glyphs = x0, []
    for ch in text:
        gid = face.get_char_index(ord(ch))

        # Undo the +1 offset that MS-Symbol applies to printable ASCII
        if is_ms_symbol and 0x20 <= ord(ch) <= 0x7E and gid:
            gid -= 1
        
        glyphs.append((gid, pen_x, y0))
        face.load_glyph(gid, freetype.FT_LOAD_DEFAULT)
        pen_x += face.glyph.advance.x / 64.0
    return glyphs

def get_first_n_glyphs(face:freetype.Face,s,e,gids):

    pen_x, glyphs = 0, []

    # string = ""
    # for i in  gids:# range(s,e):
    #     glyphs.append(cairo.Glyph(i, pen_x, 30))
    #     if ch > 0 :
    #         string += chr(ch)
    #     pen_x += 30 

    ch , gid  = face.get_first_char()
    string = ""
    while len(glyphs) == 0 or gid != 0:
        glyphs.append((gid, pen_x, 30))
        if ch > 0 :
            string += chr(ch)
        pen_x += 30 
        ch, gid = face.get_next_char(ch, gid)
    return glyphs,string
# ------------------------------------------------------------
# 4.  Draw the first N printable glyphs to a PNG
# ------------------------------------------------------------


def draw_first_n_glyphs(font_path,gids,  out_png="glyphs.png",s = 0 , e = 10):
    face_ft   = freetype.Face(font_path)

    face_ft.select_charmap(CURR_ENCODING) 
    font_size = 40
    # glyphs    = text_to_glyphs(
    #     ''.join(chr(cp) for cp in range(0x20, 0x20 + n)),
    #     face_ft, font_size, x0=0, y0=font_size)
    glyphs, raw_string    = get_first_n_glyphs(face_ft,s,e,gids)
    # build a Cairo face & surface
    face_cairo = create_cairo_font_face_for_file(font_path, 0)
    # width  = int(sum(face_ft.get_advance(g[0], 0) for g in glyphs)) + 20
    width = 2000
    height = font_size * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1); ctx.paint()     # white bg
    ctx.set_font_face(face_cairo)
    ctx.set_font_size(font_size)
    ctx.set_source_rgb(0, 0, 0)                  # black text
    # glyphs = [ ctx.get_scaled_font().text_to_glyphs(g[1],g[2],g[0],False) for g in glyphs]
    glyphs2 = ctx.get_scaled_font().text_to_glyphs(0,30,raw_string,False)
    print("compareing actual Glpyhs_id (used by cairo ) vs glyph_ids (returned from freetype)")
    # for i in range(len(glyphs2)):
    #     print("actual   glyphs", glyphs2[i][0])
    #     print("freetype glyphs", glyphs[i][0] )
    #     try:
    #         print("ansi codec",raw_string[i].encode("ansi"), "unicode", raw_string[i].encode("utf-8"))
    #     except Exception as e:
    #         print("ERROR: char is ", raw_string[i])
    #     print("___")
    ctx.show_glyphs(glyphs)
    # text = "".join(chr(g[0]) for g in glyphs) 
    # ctx.move_to(0, 30)
    # ctx.show_text(text)
    surface.write_to_png(out_png)
    print(f"Wrote {out_png}")

def char_to_glyph_name(ch):
    codepoint = ord(ch)
    return UV2AGL.get(codepoint, None)
def dump_cairo_charmap(face, ft_face_ptr,unlock):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 60)
    ctx      = cairo.Context(surface)
    # face ,  ft_face_ptr, unlock =  create_cairo_font_face_for_file(font_path, 0)
    ctx.set_font_face(face)
    ctx.set_font_size(48)
    # ------------------------------------------------------------------
    name2gid, cmap2gid = build_gid_map_from_cairo(ctx,ft_face_ptr,unlock)
    print("‘A’ in Cairo slot :", name2gid.keys()) # → 36 (your “actual”)
    print("cmap-gid 1 →")      
    pprint.pprint( cmap2gid)

if __name__ == "__main__":
    
    for f in os.listdir("temp"):
        FONT_PATH   = r"D:\Software\Fonts\0xProto\0xProtoNerdFont-Bold.ttf"
        FONT_TYPE1 = f"temp\\{f}"
        FONT_PATH = FONT_TYPE1
        FONT_SIZE   = 30
        LINE_HEIGHT = 30

        start = int( f.split(".")[0].split("_")[-1])
        gids  = dump_glyph_table(FONT_PATH, 0)
        # glyphs = [cairo.Glyph(cha) for x in gnames] 
        # gids = [ g + start for g in gids]
        end = start + len(gids)
        print("drawing image for number of .. ", end - start , " chars")
        draw_first_n_glyphs(FONT_PATH,gids,  f"output\\glyphs_{f.split('.')[0]}.png",s =start, e = end  )
        # dump_cairo_charmap(FONT_PATH)
        #
        print("\n\n")


