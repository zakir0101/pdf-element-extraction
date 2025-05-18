from math import isnan
from pathlib import Path
import os
import platform
import re
import subprocess
from .pdf_encoding import PdfEncoding as pnc
from typing import Callable, Tuple
import cairo
import json
from pypdf.generic import PdfObject, IndirectObject
from pypdf import PdfReader

from .pdf_utils import open_image_in_irfan, kill_with_taskkill
from engine import winansi
from .create_cairo_font import create_cairo_font_face_for_file
import pprint

# from fontTools.ttLib import TTFont
from os.path import sep
from fontTools.agl import UV2AGL
import freetype

from .winansi import winansi_encoding

UNIC = freetype.FT_ENCODINGS.get("FT_ENCODING_UNICODE")
ADBC = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_CUSTOM")
ADBS = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_STANDARD")
ADBE = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_EXPERT")
ADBL = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_LATIN1")

ENC_LIST = [ADBC, ADBE, ADBS, ADBL, UNIC]


if os.name == "nt":  # Windows
    ansi = "ansi"
else:
    ansi = "iso_8859_1"


class PdfFont:

    TYPE0 = ["/Type0"]
    TYPE1 = ["/Type1", "/TrueType"]
    TYPE3 = ["/Type3"]
    SUPPORTED_TYPES = ["/Type0", "/Type1", "/TrueType", "/Type3"]
    FONT_DIR = Path(f".{sep}Fonts")
    SYSTEM_FONTS = None

    def __init__(
        self,
        font_name: str,
        font_object: PdfObject | None,
        reader: PdfReader,
        process_glyph_stream: Callable,
        depth: int,
    ) -> None:

        if font_object is None:
            raise ValueError("Font object is None")

        self.font_type: str = str(font_object.get("/Subtype"))
        if self.font_type not in self.SUPPORTED_TYPES:
            raise Exception(
                f"font type {self.font_type} is NOT supported yet !!"
            )

        self.is_type0, self.is_type3 = False, False
        font_dict = self.create_font_dict(font_object, reader)
        self.font_dict = font_dict

        # ************ GENERALL *****************
        # ------------

        self.font_object = font_dict
        self.font_name: str = font_name
        self.depth = depth
        self.base_font: str = str(font_dict.get("/BaseFont", "/UnkownBase"))
        self.first_char: int = int(font_dict.get("/FirstChar", 1))
        self.last_char: int = int(font_dict.get("/LastChar", -1))
        self.encoding = font_dict.get("/Encoding")
        self.process_glyph_stream = process_glyph_stream
        self.should_skip_rendering = False
        self.scaling_factor = None
        self.use_toy_font = False
        self.use_system_font = False
        self.adjust_glyph_width = False

        # ************* DiFF map ***********************
        # ---------
        self.diff_map = self.create_diff_map_dict(font_dict)
        # print(self.diff_map)

        # ************* ToUnicode Map *******************
        # ----------
        self.cmap_data = None
        self.valid_ranges = None
        self.cid_to_unicode = {}

        self.cid_to_unicode, self.valid_ranges = (
            self.create_tounicode_map_dict(font_dict)
        )

        # ************* Width Map *******************
        # ----------
        self.width = self.create_width_map(font_dict)

        # ************ FONT DATA VARS *********************
        # ------------ TYPE0 , TYPE1
        self.font_face = None
        self.ft_encoding, self.ft_face = None, None
        self.has_char_map = False
        self.font_path = None
        self.cid_to_gid = {}
        self.char_to_gid = {}
        self.symbol_to_gid = {}
        self.font_desc = font_dict.get("/FontDescriptor")
        # ------------ TYPE3
        self.char_procs = font_dict.get("/CharProcs", {})
        self.font_matrix = cairo.Matrix(
            *font_dict.get("/FontMatrix", [0.001, 0, 0, 0.001, 0, 0])
        )
        self.glyph_cache = {}
        # ------------ Embeded Font File ----------------------------
        # for :  typ1,type0,TrueType,OpenType
        # -------------

        if (
            self.font_type
            in [
                *self.TYPE1,
                *self.TYPE0,
            ]
            # and "/FontDescriptor" in font_dict
        ):  # "/FontDescriptor" in font_dict:
            self.load_type1_type0_font_data(font_dict, reader)
        # -------------- Font glyph Stream ---------------------
        # only: for TYPE3 fonts
        # -------------------
        elif self.font_type in self.TYPE3:  # "/CharProcs" in font_dict:
            self.is_type3 = True
            self.load_type3_font_data(font_dict)

        if self.use_system_font:
            self.load_font_from_system_fonts()

        if self.use_toy_font:
            self.use_system_font = False
            self.font_family = "Sans"
            self.font_style = None
            self.set_font_style_and_family()
            self.slant = cairo.FONT_SLANT_NORMAL
            self.weight = cairo.FONT_WEIGHT_NORMAL
            self.setup_cairo_toy_font()

    def set_font_style_and_family(
        self,
    ):
        parts = self.base_font.lstrip("/").split("+", 1)
        if len(parts) == 2:
            prefix, font_name = parts
        else:
            font_name = parts[0]
        font_parts = font_name.split(",")
        if len(font_parts) > 1:
            self.family = font_parts[0]
        self.style = font_parts[1:] if len(font_parts) > 1 else font_parts
        self.style = list(map(str.lower, self.style))

    def setup_cairo_toy_font(self):
        for style_part in self.style:
            style = style_part.lower()
            if "italic" in style:
                self.slant = cairo.FONT_SLANT_ITALIC
            elif "oblique" in style:
                self.slant = cairo.FONT_SLANT_OBLIQUE
            if "bold" in style:
                self.weight = cairo.FONT_WEIGHT_BOLD

    def create_font_dict(self, font_object: PdfObject, reader):
        font_dict = {
            key: (
                value
                if not isinstance(value, IndirectObject)
                else reader.get_object(value)
            )
            for key, value in font_object.items()
            if not key.startswith("_")
        }
        if "/DescendantFonts" in font_dict:
            self.is_type0 = True
            des_list = font_dict.get("/DescendantFonts")
            for desc_i in des_list:
                if desc_i and isinstance(desc_i, IndirectObject):
                    desc_i = reader.get_object(desc_i)
                desc_i = {
                    key: (
                        value
                        if not isinstance(value, IndirectObject)
                        else reader.get_object(value)
                    )
                    for key, value in desc_i.items()
                    if not key.startswith("_")
                }
                font_dict.update(desc_i)
        return font_dict

    def create_width_map(self, font_dict: dict):
        self.widths = None
        if self.font_type in [*self.TYPE1, *self.TYPE3]:  # not self.is_type0:
            self.default_width = font_dict.get("/FontDescriptor", {}).get(
                "/MissingWidth", None
            )
            widths = font_dict.get("/Widths")
            # if isinstance(widths, IndirectObject):
            #     widths = reader.get_object(widths)
            if isinstance(widths, list):
                if len(widths) > 1:
                    self.widths: list[int] = [int(x) for x in widths]
                else:
                    self.widths = widths[0]
            elif isinstance(widths, (int, float, str)):
                self.widths = widths
            else:  # if self.widths is None:
                raise Exception("Width is None or has different format !!")
        elif self.font_type in self.TYPE0:
            self.default_width = font_dict.get("/DW", 1000)
            widths = font_dict.get("/W", [])
            # if isinstance(widths, IndirectObject):
            #     widths = reader.get_object(widths)
            self.widths = {}
            i = 0
            while i < len(widths) - 1:
                el = int(widths[i])
                n_el = widths[i + 1]
                if isinstance(n_el, list):
                    for j in range(len(n_el)):
                        self.widths[el + j] = n_el[j]
                    i = i + 2
                elif i + 2 < len(widths):
                    n_el = int(n_el)
                    n2_el = widths[i + 2]
                    if isinstance(n2_el, list):
                        if len(n2_el) == 1:
                            n2_el = n2_el[0]
                        else:
                            raise Exception
                    for j in range(el, n_el + 1):
                        self.widths[j] = n2_el
                    i = i + 3
        else:

            raise Exception(
                f"font type {self.font_type} is NOT supported yet !!"
            )

        return self.widths

    def load_type3_font_data(self, font_dict):
        proc = self.char_procs
        self.base_font = "/Type3"
        if len(proc.keys()) > 1 or "/space" not in proc:
            """for testing purposes"""
            print(proc)
            raise Exception("None-Empty Type3 font")

    def load_type1_type0_font_data(self, font_dict, reader):
        # print(font_dict)
        font_desc = self.font_desc
        not_found = True
        for font_file_key in ["/FontFile", "/FontFile2", "/FontFile3"]:
            if font_file_key in font_desc:
                not_found = False
                # ************* initilize dir *****************
                # -----------

                font_file = self.font_desc[font_file_key]
                font_path = self.save_embeded_font_to_file(font_file, reader)
                ft_face = freetype.Face(font_path)
                self.font_path = font_path
                self.ft_face = ft_face
                if not self.is_type0:
                    self.select_char_map_for_font()
                if self.has_char_map:
                    (
                        self.cid_to_gid,
                        self.char_to_gid,
                        self.symbol_to_gid,
                    ) = self.create_glyph_map_dicts(font_path)

        if not_found:

            self.use_system_font = True
            self.adjust_glyph_width = True

    def save_embeded_font_to_file(self, font_file, reader):
        temp_dir = "temp"
        font_path = (
            temp_dir + sep + self.font_name + "_" + str(self.depth) + ".ttf"
        )
        if not os.path.exists(temp_dir):
            os.mkdir(temp_dir)
        elif os.path.exists(font_path):
            os.remove(font_path)

        if isinstance(font_file, IndirectObject):
            font_file = reader.get_object(font_file)
        font_data = font_file.get_data()
        file = open(font_path, "bw")
        file.write(font_data)
        file.flush()
        file.close()
        return font_path

    def select_char_map_for_font(self):
        if not self.is_type0:
            try:
                # for enc in ENC_LIST:
                #     try:
                #         self.ft_face.select_charmap(enc)
                #         self.ft_encoding = enc
                #         break
                #     except Exception as e:
                #         pass
                if self.ft_encoding is None:
                    self.ft_face.set_charmap(self.ft_face.charmaps[0])
                    self.ft_encoding = self.ft_face.charmap.encoding
                self.has_char_map = True
            except Exception as e:
                print(e)
                print(
                    f"could not select cmap for font {self.font_name}: {self.base_font} "
                )
                self.ft_encoding = None
        else:
            self.ft_encoding = None

    def is_char_code_valid(self, cid):
        if self.valid_ranges is None:
            if self.default_width or self.missing_width:
                return True  # just for safty

        for start, end in self.valid_ranges:
            if start <= cid <= end:
                return True
        return False

    def create_tounicode_map_dict(self, font_dict):

        if "/ToUnicode" not in font_dict:
            return {}, None
        tounicode = font_dict["/ToUnicode"]
        data = tounicode.get_data().decode("utf-8")
        self.cmap_data = data
        tokens = self.tokenize_cmap(data)

        cid_map = {}
        codespace_ranges = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == "begincodespacerange":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    # Parse <start> <end> pairs
                    start = int(tokens[i + 1], 16)
                    end = int(tokens[i + 4], 16)
                    codespace_ranges.append((start, end))
                    i += 6  # Skip past '<', start, '>', '<', end, '>'
                # Skip past "endcodespacerange"
                while i < len(tokens) and tokens[i] != "endcodespacerange":
                    i += 1
                i += 1
            elif token == "beginbfchar":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    cid = int(tokens[i + 1], 16)
                    unicode_char = bytes(int(tokens[i + 4], 16)).decode(
                        "utf-8"
                    )
                    cid_map[cid] = unicode_char
                    i += 6  # Skip '<', cid, '>', '<', unicode, '>'
            elif token == "beginbfrange":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    cid_start = int(tokens[i + 1], 16)
                    cid_end = int(tokens[i + 4], 16)
                    uni_start = int(tokens[i + 7], 16)
                    for offset in range(cid_end - cid_start + 1):
                        cid = cid_start + offset
                        cid_map[cid] = bytes(uni_start + offset).decode(
                            "utf-8"
                        )
                    i += 9  # Skip '<', start, '>', '<', end, '>', '<', uni_start, '>'
            i += 1
        return cid_map, codespace_ranges or None

    def tokenize_cmap(self, data):
        tokens = []
        current = []
        in_comment = False
        for char in data:
            if char == "%":
                in_comment = True
            if in_comment:
                if char == "\n":
                    in_comment = False
                continue
            if char.isspace():
                if current:
                    tokens.append("".join(current))
                    current = []
            elif char in "<>":
                if current:
                    tokens.append("".join(current))
                    current = []
                tokens.append(char)
            else:
                current.append(char)
        if current:
            tokens.append("".join(current))
        return tokens

    def create_glyph_map_dicts(self, font_path):
        char_to_gid = {}
        symbol_to_gid = {}
        code_to_gid = {}
        if "T1_1" in self.font_name:
            for cmap in self.ft_face.charmaps:
                print(cmap.encoding)
        # self.ft_face.set_charmap(cmap)

        for (
            cp,
            raw_gid,
        ) in self.ft_face.get_chars():  # iterate the cmap

            if raw_gid == 0:
                continue

            code_to_gid[cp] = raw_gid
            gname0 = self.diff_map.get(cp, "").replace("/", "")

            # if gname0:
            #     symbol_to_gid[gname0] = raw_gid
            #     continue

            # if "T1_4" in self.font_name:
            #     print("+++", gname0, cp, raw_gid)

            gname = None
            if self.ft_face._has_glyph_names():
                try:
                    gname = self.ft_face.get_glyph_name(raw_gid)
                    gname = pnc.bytes_to_string(gname)
                except Exception:
                    gname = ""
            elif gname0:
                gname = gname0
            elif not gname:
                gname = self.get_symbol_name_from_char_code(cp)

            if gname and gname != ".notdef":
                symbol_to_gid[gname] = raw_gid
            if cp <= 255:
                char = pnc.int_to_char(cp)
                if (
                    char_to_gid.get(char) is not None
                    and char_to_gid.get(char) != raw_gid
                ):
                    raise Exception("2 code with same char representation")
                char_to_gid[char] = raw_gid

        return code_to_gid, char_to_gid, symbol_to_gid

    def get_cairo_font_face(self):
        """Get a Cairo font face from the embedded font if available"""
        self.font_face = create_cairo_font_face_for_file(
            self.font_path, encoding=self.ft_encoding
        )
        return self.font_face

    def create_diff_map_dict(self, font_dict: dict, debug=False):
        if (
            "/Differences" not in self.encoding
        ):  # isinstance(self.encoding, IndirectObject):
            return {}
        font_diff: PdfObject = self.encoding.get("/Differences")
        current_index = 1
        diff_map = {}
        for symbole in font_diff:
            sym = symbole
            if isinstance(sym, int):
                current_index = sym  # if int(sym) > 0 else 1
            else:
                diff_map[current_index] = sym
                current_index += 1
        if debug:
            print(diff_map)
        return diff_map

    def get_char_code_from_match(
        self, char: str, symbol: str, prev_symbol: str
    ) -> Tuple[int, int]:
        if char is not None:
            char_code = pnc.char_to_int(char)
            # char_name = UV2AGL.get(char_code,None)
            # if char_name and self.dif
        elif self.use_toy_font or not self.is_type0:
            symbol = symbol.lstrip("\\")
            char_code = int(symbol, 8)
        else:
            if prev_symbol is None:
                raise Exception("missing prev symbol in composite font")
            high_byte = int(prev_symbol.strip("\\"), 8)
            low_byte = int(symbol.strip("\\"), 8)
            char_code = (high_byte << 8) | low_byte
            pass

        return char_code

    def get_default_ansi(self, char_code_base_10: int):
        return bytearray([char_code_base_10]).decode("ansi")

    def render_glyph_for_type3_font(self, char_name, fill_color):
        # char_name = self.get_symbol_name_from_char_code(char_code)
        stream_bytes = self.char_procs[char_name].get_data()
        stream = pnc.bytes_to_string(stream_bytes)
        bbox = self.font_dict.get("/FontBBox", [0, 0, 1000, 1000])
        # print("bbox", bbox)
        # print("font_matrix", self.font_matrix)
        # for key in self.char_procs.keys():
        #     print("key", key)
        # print(len(self.char_procs.keys()))
        rect = cairo.Rectangle(*bbox)
        recorder = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
        # recorder = cairo.ImageSurface(
        #     cairo.FORMAT_ARGB32, bbox[2] * 1000, bbox[3] * 1000
        # )
        ctx = cairo.Context(recorder)
        ctx.set_source_rgb(*[1, 1, 1])
        ctx.paint()
        ctx.set_source_rgb(*[0, 0, 0])
        ctx.move_to(0, 0)
        ctx.scale(1000, 1000)
        self.process_glyph_stream(stream, ctx)
        # imp = f"output{sep}recorded_surface.png"
        # recorder.write_to_png(imp)
        # open_image_in_irfan(imp)
        return recorder

    # def _swap_glyph_operators(self, ctx):
    #     original = {}
    #     original["fill"] = ctx.fill
    #     original["stroke"] = ctx.stroke
    #     original["clip"] = ctx.clip
    #     ctx.fill = lambda: None  # No-op fill
    #     ctx.stroke = lambda: None  # No-op stroke
    #     ctx.clip = lambda: None  # No-op clip
    #     return original
    #
    # def _restore_operators(self, original):
    #     ctx = self.ctx
    #     ctx.fill = original["fill"]
    #     ctx.stroke = original["stroke"]
    #     ctx.clip = original["clip"]

    # def _extract_path_from_surface(self, ctx: cairo.Context, surface):
    #     """Convert recording surface operations to a reusable path"""
    #     path = ctx.cop
    #     surface.replay_to_path(path)
    #     return path

    # def _process_glyph_content(self, char_name, ctx):
    #     """Process glyph content stream while preserving path"""
    #     original_ctx = self.ctx
    #     original_matrix = self.cm_matrix.copy()
    #
    #     try:
    #         # Redirect to glyph context
    #         self.ctx = ctx
    #         self.cm_matrix = Matrix.identity()
    #
    #         # Process glyph content stream
    #         stream = self.char_procs[char_name].get_data()
    #         self.process_commands(stream)
    #
    #         # Finalize path
    #         ctx.new_path()  # Ensures path closure
    #     finally:
    #         # Restore original context
    #         self.ctx = original_ctx
    #         self.cm_matrix = original_matrix

    def get_glyph_for_type3(self, char_code, fill_color):
        if char_code in self.glyph_cache:
            return self.glyph_cache[char_code]
        # char_name = self.diff_map.get(char_code, ".notdef")
        char_name = self.get_symbol_name_from_char_code(char_code)
        if char_name[1] != "/":
            char_name = "/" + char_name
        if char_name not in self.char_procs:
            print(f"error: char_code: {char_code}, char_name: {char_name}")
            raise Exception("char name for type3 font not found")

            return None
        path = self.render_glyph_for_type3_font(char_name, fill_color)
        self.glyph_cache[char_code] = path  # (path, width)
        return self.glyph_cache[char_code]

    def get_char_width_from_code(self, char_code: int):
        if isinstance(self.widths, (int, float)):
            return self.widths
        if not self.is_type0:  # type1,type3 has width as list
            if char_code >= self.first_char and char_code <= self.last_char:
                width = self.widths[char_code - self.first_char]
                return width if (width is not None) else self.default_width

            else:
                return None
                raise Exception(
                    f"char code {char_code}, for char {chr(char_code)} , does not have width mapping"
                )

        else:
            width = self.widths.get(char_code)
            if width is None and self.is_char_code_valid(char_code):
                width = self.default_width
            return width

    def get_glyph_id_from_char_code(self, char_code: int, is_symbol: bool):
        symbol_name = None
        if self.is_type0 or self.is_type3 or self.use_toy_font:
            glyph_id = char_code
            symbol_name = f"\\{char_code}"
        else:  # type0
            if is_symbol:
                symbol_name = self.diff_map.get(char_code, "").replace(
                    "/", ""
                ) or self.get_symbol_name_from_char_code(char_code)
                glyph_id = self.symbol_to_gid.get(symbol_name)
            else:
                glyph_id = self.cid_to_gid.get(char_code)
                symbol_name = self.diff_map.get(char_code, "")
                if glyph_id is None:
                    glyph_id = self.symbol_to_gid.get(symbol_name)

                if char_code == 55:
                    print("+++, 7 (ord=55)=", glyph_id)

            if glyph_id is None and symbol_name:
                c_ids: list[int] = list(self.diff_map.keys())
                char_index = c_ids.index(char_code)
                for i, ch_code in enumerate(reversed(c_ids[:char_index])):
                    ch_glyph_id = self.cid_to_gid.get(ch_code)
                    if ch_glyph_id:
                        print(
                            f"+++ found glyph_id={ch_glyph_id}, for ch_code={ch_code}"
                        )
                        glyph_id = ch_glyph_id + i + 1
                        break

            if glyph_id is None:
                glyph_id = char_code

        return glyph_id, symbol_name

    def get_symbol_name_from_char_code(self, char_code):
        symbol = UV2AGL.get(char_code, None)
        if not symbol and char_code < len(winansi_encoding):
            symbol = winansi_encoding[char_code]
        if symbol:
            return symbol.lstrip("/")
        else:
            return "<unavailable>"

    def debug_font(self):
        print(f"\n\n****************** {self.font_name} ******************")
        print(f"               ****************** ")

        font_size = 20
        width = 500
        height = 700  # y + 50
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()  # white bg
        ctx.set_source_rgb(0, 0, 0)  # black text
        ctx.set_font_size(font_size / 2)

        pen_x, glyphs = 20, []
        cid_glyphs = []
        y = 30
        counter = 0
        curr_dict = (
            self.cid_to_gid if not self.is_type0 else self.cid_to_unicode
        )

        items = list(sorted(curr_dict.items(), key=lambda x: x[0]))
        for cid, gid_or_unic in items:
            # if not
            #     continue
            prefix = ""
            if counter % 12 == 0:
                y = y + 50
                pen_x = 20
                prefix = "\n"
            if y > 1000:
                break
            if self.is_type0:
                if gid_or_unic == " ":
                    gid_or_unic = "Space"
                print(f"{prefix}{gid_or_unic:7}", end=" ")
                gid = cid
                print(cid)
                code = pnc.byte_to_octal(int.to_bytes(cid))
                ctx.move_to(pen_x, y - 19)

            else:
                o = chr(cid)
                if o == " ":
                    o = "Space"
                print(f"{prefix}{o:>7}", end=" ")
                gid = gid_or_unic  # self.cid_to_gid[cid]
                code = str(cid)
                ctx.move_to(pen_x + 10, y - 14)

            glyphs.append(cairo.Glyph(gid, pen_x, y))
            ctx.show_text(code)

            pen_x += 50
            counter += 1
        if counter == 0:
            pprint.pprint(self.cmap_data)
            pprint.pprint(self.cid_to_unicode)
        face_cairo = self.get_cairo_font_face()

        ctx.move_to(0, 0)
        ctx.set_font_face(face_cairo)
        ctx.set_font_size(font_size)
        ctx.show_glyphs(glyphs)

        ctx.show_glyphs(cid_glyphs)

        out_png = f"output{sep}output.png"
        surface.write_to_png(out_png)
        open_image_in_irfan(out_png)
        a = input("\n\npress any key to continue")
        kill_with_taskkill()

    # ************************************************
    # ************* Attention  ***********************
    # xxxxxxxxxxxx DONT DELETE CODE BELOW xxxxxxxxxxxx

    def load_font_from_system_fonts(self):
        """
        the following code is basis for the futer implementation where we:
        1- detect all missing font files from all exam
        2- find a free similar font that match each missing font file
        3- collect all the found similar font in the Fonts dir ..
        4- create a table that map each "missing" pdf font to a free one
        5- use the free font .

        Note:
            currently we will uses cairo toy font instead !!

        """
        if self.base_font not in self.FONT_SUBSTITUTION_MAP:
            raise Exception(
                f"No alternative found for font {self.base_font},{self.font_name}\n"
                + f"font:{self.font_dict}"
            )

        self.base_font = self.FONT_SUBSTITUTION_MAP[self.base_font]
        self.font_path = f"Fonts{sep}{self.base_font}"
        if not os.path.exists(self.font_path):
            raise Exception("System Font not found on Path")

        ft_face = freetype.Face(self.font_path)
        self.ft_face = ft_face
        if not self.is_type0:
            self.select_char_map_for_font()
        if self.has_char_map:
            (
                self.cid_to_gid,
                self.char_to_gid,
                self.symbol_to_gid,
            ) = self.create_glyph_map_dicts(self.font_path)
        pass

    FONT_SUBSTITUTION_MAP = {
        # Times Family -> Liberation Serif
        "/TimesNewRomanPSMT": "LiberationSerif-Regular.ttf",
        "/Times-Roman": "LiberationSerif-Regular.ttf",
        "/TimesNewRomanPS-ItalicMT": "LiberationSerif-Italic.ttf",
        "/Times-Italic": "LiberationSerif-Italic.ttf",
        "/TimesNewRomanPS-BoldMT": "LiberationSerif-Bold.ttf",
        "/Times-Bold": "LiberationSerif-Bold.ttf",
        "/TimesNewRomanPS-BoldItalicMT": "LiberationSerif-BoldItalic.ttf",
        "/Times-BoldItalic": "LiberationSerif-BoldItalic.ttf",
        # Helvetica Family -> Liberation Sans
        "/Helvetica": "LiberationSans-Regular.ttf",
        "/Helvetica-Bold": "LiberationSans-Bold.ttf",
        "/Helvetica-Oblique": "LiberationSans-Italic.ttf",  # Using Italic for Oblique
        # Arial Family -> Liberation Sans
        "/ArialMT": "LiberationSans-Regular.ttf",
        "/Arial": "LiberationSans-Regular.ttf",  # Explicitly adding /Arial
        "/Arial-ItalicMT": "LiberationSans-Italic.ttf",
        "/Arial-BoldMT": "LiberationSans-Bold.ttf",
        # Courier Family -> Liberation Mono
        "/CourierNewPSMT": "LiberationMono-Regular.ttf",
        # Verdana Family -> DejaVu Sans
        "/Verdana": "DejaVuSans.ttf",  # Or DejaVuSans-Book.ttf; the base TTF should work.
        "/Verdana-Italic": "DejaVuSans-Oblique.ttf",  # Or the Italic style within DejaVuSans.ttf
        # Symbol Family -> OpenSymbol
        "/Symbol": "OpenSymbol.ttf",
    }
