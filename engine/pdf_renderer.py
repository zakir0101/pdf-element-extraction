import enum
import re
import string


from engine.pdf_utils import open_image_in_irfan, kill_with_taskkill
from .pdf_operator import PdfOperator
from .engine_state import EngineState
import cairo
import subprocess
from cairo import Context, ImageSurface
import os
from .pdf_detectors import Sequence, Symbol, BaseDetector

SEP = os.path.sep

doty = -30


class BaseRenderer:
    def __init__(
        self, state: EngineState, main_detector: BaseDetector
    ) -> None:
        self.state: EngineState = state
        self.default_char_width = 10

        self.surface: ImageSurface | None = None
        self.ctx: Context | None = None
        self.skip_footer = True
        self.page_number = -1
        self.main_detector: BaseDetector = main_detector
        self.max_dots = 20

        self.functions_map = {
            "TJ": self.draw_string_array,
            "Tj": self.draw_string,
            "'": self.draw_string,
            '"': self.draw_string,
            "m": self.move_line_to,
            "l": self.draw_line_to,
            "y": self.draw_bezier_y_v,
            "v": lambda x: self.draw_bezier_y_v(x, is_y_type=False),
            "c": self.curve_to,
            "re": self.draw_rectangle,
            "f": self.fill_path,
            "f*": lambda x: self.fill_path(x, False, True),
            "S": self.stroke_path,
            "s": lambda x: self.stroke_path(x, False, True),
            "B": lambda x: self.fill_and_stroke(x, False, False),
            "B*": lambda x: self.fill_and_stroke(x, False, True),
            "b": lambda x: self.fill_and_stroke(x, True, False),
            "b*": lambda x: self.fill_and_stroke(x, True, True),
            "W": lambda x: self.clip_path(x, False),
            "W*": lambda x: self.clip_path(x, True),
            "h": self.close_path,
            "EI": self.draw_inline_image,
            "W": self.draw_clip,
            "n": self.end_path,
            "q": self.save_state,
            "Q": self.restore_state,
            # "EI": self.test_surface_paint,
            # Existing operators...
            "ET": self.end_text,
            "BDC": lambda x: ("", True),  # not relevant
            "EMC": lambda x: ("", True),  # not relevant
            "i": lambda x: ("", True),  # not supported by cairo
        }

        self.sync_functions_map = [
            #     ( [ "cs", "CS", "k", "K", "g", "G", "rg", "RG", "sc", "SC", "scn", "SCN", ], self.sync_color,),
            (
                [
                    "Tm",
                    "cm",
                    "BT",
                    "ET",
                    "q",
                    "Td",
                    "TD",
                    "T*",
                    "'",
                    '"',
                    "Tz",
                    "Ts",
                ],
                self.sync_matrix,
            )
        ]

    def initialize(self, width: int, height: int, page: int) -> None:
        """Initialize the Cairo surface and context."""
        self.width = width
        self.height = height
        self.page_number = page
        self.footer_y = height * 0.95
        self.header_y = height * 0.06
        self.surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.width, self.height
        )
        # self.surface.set_device_scale(3.0, 3.0)  # Doubles the effective resolution
        self.ctx = cairo.Context(self.surface)
        self.ctx.set_source_rgb(1, 1, 1)  # White
        self.ctx.paint()
        self.ctx.set_source_rgb(0, 0, 0)  # Black
        pass

    def close_path(self, _: PdfOperator):
        """Close the current subpath"""
        self.ctx.close_path()
        return "", True

    def curve_to(self, cmd: PdfOperator):
        """Draw a cubic Bezier curve"""
        x1, y1, x2, y2, x3, y3 = cmd.args
        self.ctx.curve_to(x1, y1, x2, y2, x3, y3)
        self.state.position = [x3, y3]
        return "", True

    def draw_bezier_y_v(self, cmd: PdfOperator, is_y_type=True):
        """Implementation of 'y' PDF operator (curved path segment)"""
        x1, y1, x3, y3 = cmd.args
        x2, y2 = (x3, y3) if is_y_type else (x1, y1)
        self.ctx.curve_to(
            x1,
            y1,
            x2,
            y2,
            x3,
            y3,
        )
        self.state.position = [x3, y3]
        return "", True

    def set_cmyk_color(self, cmd: PdfOperator, is_fill: bool):
        """Set CMYK color"""
        # Color conversion is handled by EngineState
        # Just need to update the context's color
        color = self.state.fill_color if is_fill else self.state.stroke_color
        self.ctx.set_source_rgb(*color)
        return "", True

    def end_text(self, _: PdfOperator):
        """End text object"""
        # Most of the work is handled by EngineState
        return "", True
        pass

    def draw_clip(self, _: PdfOperator):
        # W operator - Set clipping path
        # Even if we don't fully implement shape rendering,
        # we should at least acknowledge the clipping path
        self.ctx.clip()
        self.ctx.new_path()
        return "", True

    def end_path(self, _: PdfOperator):
        # n operator - End path without filling/stroking
        self.ctx.new_path()
        return "", True

    def save_state(self, _: PdfOperator):
        # q operator
        # handled by EngineState
        self.ctx.save()
        return "", True
        pass

    def restore_state(self, _: PdfOperator):
        # Q operator
        # handled by EngineState
        self.ctx.restore()
        # self.sync_matrix()
        return "", True
        pass

    def get_scale(self, character, width):
        extents = self.ctx.text_extents(character)
        natural_width = extents.x_advance
        ratio = extents.y_advance / natural_width or 1
        h_scale = 1.0 if natural_width == 0 else width / natural_width
        return h_scale, ratio

    def get_glyph_scale(self, gid, width):
        extents = self.ctx.glyph_extents([cairo.Glyph(gid, 0, 0)])
        natural_width = extents.x_advance
        if natural_width == 0:
            natural_width = self.default_char_width
        ratio = extents.y_advance / natural_width or 1
        h_scale = 1.0 if natural_width == 0 else width / natural_width
        return h_scale, ratio

    def draw_string(self, cmd: PdfOperator):
        # print("drawing single text ", text)
        return self.draw_string_array(cmd, is_single=True)

    def count_dots(self, char_seq):
        global doty
        sym: Symbol = char_seq[0]
        if abs(sym.y - doty) < sym.h * 0.6:
            return True
        dot = "."
        is_dot_only = (
            len([sym for sym in char_seq if dot in sym.ch]) > self.max_dots
        )
        if is_dot_only:
            doty = sym.y
        else:
            doty = -30

        return is_dot_only

    def should_skip_sequence(self, char_seq):

        if char_seq is None:
            return True
        if len(char_seq) == 0:
            return True
        if self.skip_footer and (
            char_seq[0].y >= self.footer_y or char_seq[0].y <= self.header_y
        ):
            return True
        if self.skip_footer and self.count_dots(char_seq):
            return True
        return False

    def draw_string_array(self, cmd: PdfOperator, is_single=False):
        glyph_array, char_seq, update_text_position = self.get_glyph_array(
            cmd, is_single
        )
        char_seq: Sequence = char_seq
        if self.should_skip_sequence(char_seq):
            update_text_position()
            return "", True
        # if self.count_dots(char_seq) < self.max_dots:
        self.draw_glyph_array(glyph_array)
        update_text_position()
        return "", True

    def get_glyph_array(self, cmd: PdfOperator, is_single=False):
        if is_single:
            text_array = [cmd.args[0]]
        else:
            text_array = cmd.args[0]

        state = self.state
        x, y = state.text_position
        font_size = state.font_size

        font = self.state.font

        char_regex1 = r"(?:\\(?P<symbol>\d{3}))|(?P<char>.)"
        # char_regex2 = r"(?:(?:^|[^\\])\\(?P<symbol>\d{3}))|(?P<char>.)"
        # char_regex2 = r"\\(?P<symbol>\d{3})(?!\d{3})|(?:\\(?P<symbol_long>\d{6})|(?P<char>(?:\\)?.))"
        # char_regex2 = r"(?P<symbol>\d{6})|(?P<char>dontFinDMeHere)"

        cairo_font_face = None
        try:
            cairo_font_face = font.get_cairo_font_face()
        except Exception as e:
            pass
            print(f"Error loading embedded font face: {e}")
            raise Exception(f"Error loading embedded font face: {e}")

        if cairo_font_face is not None:
            self.ctx.set_font_face(cairo_font_face)
        else:
            print(" embeded font NOT found ")
            self.ctx.select_font_face(
                font.family,
                font.slant,
                font.weight,
            )

        self.ctx.set_font_size(font_size)

        c_spacing = state.character_spacing
        w_spacing = state.word_spacing

        m_c = self.state.get_current_matrix()
        glyph_array = []
        char_array = []

        for element in text_array:
            if isinstance(element, float):
                dx = state.convert_em_to_ts(float(element))
                x -= dx
            elif isinstance(element, str):
                element = self.clean_text(element)

                last_char = None
                for word in re.split(
                    r"([ ]+)", element, flags=re.DOTALL | re.MULTILINE
                ):
                    if word.isspace():
                        x += w_spacing
                    for i, char_or in enumerate(
                        re.finditer(char_regex1, word)
                    ):
                        char_or: re.Match = char_or
                        if font.is_composite and char_or.group("symbol"):
                            if i % 2 == 1:
                                glyph_id, char_width, char = (
                                    self.get_glyph_id_for_char(
                                        char_or, last_char
                                    )
                                )
                                last_char = None
                            else:
                                last_char = char_or
                                continue
                        else:
                            glyph_id, char_width, char = (
                                self.get_glyph_id_for_char(char_or, None)
                            )

                        if glyph_id is None:
                            continue
                        glyph_obj = cairo.Glyph(glyph_id, x, y)
                        glyph_array.append(glyph_obj)
                        x0, y0 = m_c.transform_point(x, y)
                        w, h = m_c.transform_distance(char_width, char_width)
                        char_array.append(Symbol(char, x0, y0, w, h))
                        x += char_width + c_spacing

            else:
                raise ValueError("Invalid text element")

        def update_on_finish():
            if is_single or True:
                self.state.text_position = [x, y]

        if len(glyph_array) == 0:
            return None, None, update_on_finish

        return glyph_array, Sequence(char_array), update_on_finish

    def get_glyph_id_for_char(
        self, char_or, prev_char: re.Match | None = None
    ):
        font = self.state.font
        char = char_or.group("char")
        symbol = char_or.group("symbol")
        prev_symbol = prev_char.group("symbol") if prev_char else None
        is_symbol = char is None

        # +++++++++++++++ for DEBUG ******************
        if not is_symbol and not char:  # check for empty match
            return None, None, None
        if is_symbol and not symbol:  # check for empty match
            return None, None, None
        if font.is_composite:
            if not is_symbol or not symbol or not prev_symbol:
                raise Exception("missing symbol[prev] for composite font")
        # ************** END DEBUG ********************

        char_code = font.get_char_code_from_match(char, symbol, prev_symbol)
        char_width = font.get_char_width_from_code(char_code)
        glyph_id, glyph_name = font.get_glyph_id_from_char_code(
            char_code, is_symbol
        )

        # if glyph_id is None:
        #     if char == "p":
        #         glyph_id = font.symbol_to_gid.get("pi")
        #         char = "pi"

        if is_symbol:
            char = glyph_name
        if char_width is None:
            pass
            print(
                "is_composite:",
                font.is_composite,
                "symbol:",
                symbol,
                "char: ",
                char,
                "last_char",
                prev_symbol,
                "glyph_id",
                glyph_id,
                "char_code",
                char_code,
                "all_widths",
                font.widths,
            )
            raise Exception("char width is None")

        char_width = self.state.convert_em_to_ts(char_width)
        return glyph_id, char_width, char

    def draw_glyph_array_old(self, glyph_array):
        self.ctx.save()
        try:
            self.ctx.move_to(0, 0)
            self.ctx.show_glyphs(glyph_array)
        except Exception as e:
            print(f"ERROR while drawing Glyph array")
            raise ValueError(e)
        self.ctx.restore()

    def draw_glyph_array(self, glyph_array):
        self.ctx.save()
        try:
            self.ctx.move_to(0, 0)
            self.ctx.glyph_path(glyph_array)
            mode = self.state.text_rendering_mode
            # fill_source = (*self.state.fill_color, self.state.fill_alpha)
            # stroke_source = (*self.state.stroke_color, self.state.stroke_alpha)

            if mode in [0, 2, 4, 6]:  # Fill modes
                # self.ctx.set_source_rgba(*fill_source)
                preserve = mode in [2, 4, 6]  # Needs preserve for stroke/clip
                self.fill_path(None, preserve)
                # (self.ctx.fill_preserve if preserve else self.ctx.fill)()

            if mode in [1, 2, 5, 6]:  # Stroke modes
                # self.ctx.set_source_rgba(*stroke_source)
                preserve = mode in [2, 5, 6]  # Needs preserve for fill/clip
                self.stroke_path(None, preserve)
                (self.ctx.stroke_preserve if preserve else self.ctx.stroke)()

            if mode in [4, 5, 6, 7]:  # Clipping modes
                self.ctx.clip()
            self.ctx.new_path()
        except Exception as e:
            print(f"ERROR while drawing Glyph array")
            # raise ValueError(e)
            return
        self.ctx.restore()

    def clean_text(self, text: str):
        text = text.replace("\\(", "(").replace("\\)", ")")
        return text

    def fill_and_stroke(
        self, cmd: PdfOperator, close: bool = False, even_odd: bool = False
    ):
        """PDF 'B' operator: Fill and stroke path, then clear it"""
        self.fill_path(cmd, True, even_odd)
        self.stroke_path(cmd, False, close)

        # self.ctx.new_path()
        return "", True

    def clip_path(self, cmd: PdfOperator, even_odd=False):
        if even_odd:
            fill_rule = cairo.FILL_RULE_WINDING
        else:
            fill_rule = cairo.FILL_RULE_EVEN_ODD

        self.ctx.set_fill_rule(fill_rule)
        self.ctx.clip()

        if even_odd:
            self.ctx.set_fill_rule(cairo.FILL_RULE_WINDING)

        return "", True

    def fill_path(
        self, cmd: PdfOperator, preserve: bool = False, even_odd=False
    ) -> None:
        """Fill the current path using Cairo."""
        if even_odd:
            fill_rule = cairo.FILL_RULE_WINDING
        else:
            fill_rule = cairo.FILL_RULE_EVEN_ODD

        self.ctx.set_fill_rule(fill_rule)
        # self.ctx.set_source_rgb(*self.state.fill_color)
        self.ctx.set_source_rgba(
            *self.state.fill_color, self.state.stroke_alpha
        )
        if preserve:
            self.ctx.fill_preserve()
        else:
            self.ctx.fill()
        if even_odd:
            self.ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
        return "", True

    def stroke_path(
        self, _: PdfOperator, preserve: bool = False, close: bool = False
    ) -> None:
        """Draw a line using Cairo."""
        if self.ctx is None:
            raise ValueError("Renderer is not initialized")
        # effective_width = self.state._get_effective_line_width()
        # self.ctx.set_line_width(effective_width)
        self.ctx.set_line_width(self.state.line_width)

        # set gray color
        # self.ctx.set_source_rgb(*self.state.stroke_color)
        self.ctx.set_source_rgba(
            *self.state.stroke_color, self.state.stroke_alpha
        )
        self.ctx.set_dash(self.state.dash_pattern, 0)
        self.ctx.set_line_cap(self.state.line_cap)
        self.ctx.set_line_join(self.state.line_join)
        self.ctx.set_miter_limit(self.state.miter_limit)
        if close:
            self.ctx.close_path()
        if preserve:
            self.ctx.stroke_preserve()
            self.ctx.new_path()
        else:
            self.ctx.stroke()
        return "", True

    def move_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.move_to(x, y)
        self.state.position = [x, x]
        return "", True

    def draw_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.line_to(x, y)
        self.state.position = [x, y]
        return "", True

    def draw_rectangle(self, cmd: PdfOperator):
        x, y, width, height = cmd.args
        self.ctx.rectangle(x, y, width, height)
        return "", True

    PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "

    def hex_escape(self, s):
        return "".join(
            c if c in BaseRenderer.PRINTABLE else r"\x{0:02x}".format(ord(c))
            for c in s
        )

    def draw_inline_image(self, cmd: PdfOperator):
        color_cs = self.state.inline_image_color_space
        if color_cs not in self.state.DEVICE_CS:
            print("trying to draw image with non-spported color-spcae")
            return "", True
            raise Exception(
                "trying to draw image with non-spported color-spcae"
            )
        data = self.state.inline_image_data
        width = self.state.inline_image_width
        height = self.state.inline_image_height
        bits_per_component = self.state.inline_image_bits_per_component
        is_mask = self.state.inline_image_mask

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        surface_data = surface.get_data()
        stride = surface.get_stride()

        if is_mask and bits_per_component == 1:
            fill_color = self.state.fill_color
            r, g, b = [int(c) for c in fill_color]

            for y in range(height):
                for x in range(width):
                    byte_index = (y * width + x) // 8
                    bit_index = 7 - ((y * width + x) % 8)

                    if byte_index < len(data):
                        bit_value = (data[byte_index] >> bit_index) & 1
                        idx = y * stride + x * 4

                        if bit_value == 0:  # Black pixel
                            surface_data[idx] = b  # Blue
                            surface_data[idx + 1] = g  # Green
                            surface_data[idx + 2] = r  # Red
                            surface_data[idx + 3] = 255  # Alpha
                        else:
                            surface_data[idx] = 0  # Blue
                            surface_data[idx + 1] = 0  # Green
                            surface_data[idx + 2] = 0  # Red
                            surface_data[idx + 3] = 0  # Alpha (transparent)
        else:
            # Handle regular image case

            bytes_per_pixel = bits_per_component // 8

            if bytes_per_pixel == 0:
                bytes_per_pixel = 1

            for y in range(height):
                for x in range(width):
                    idx_out = y * stride + x * 4
                    idx_in = (y * width + x) * bytes_per_pixel

                    if idx_in + bytes_per_pixel <= len(data):
                        # Read pixel value based on bits_per_component
                        if (
                            bits_per_component <= 8
                        ):  # assume that its always == 8 (< 8 not supported)
                            if color_cs == "/DeviceGray":
                                pixel = data[idx_in]
                                pixel = (pixel * 255) // (
                                    (1 << bits_per_component) - 1
                                )
                                surface_data[idx_out] = pixel  # Blue
                                surface_data[idx_out + 1] = pixel  # Green
                                surface_data[idx_out + 2] = pixel  # Red
                                surface_data[idx_out + 3] = 255  # Alpha
                            elif color_cs == "/DeviceRGB":
                                # TODO: extract the 3 values r,g,b from the single byte
                                pass

                            elif color_cs == "/DeviceCMYK":
                                # TODO: extract the 4 values c,m,y,k from the single byte
                                pass

                            else:
                                raise Exception("Why are you here !!!")
                        else:
                            if color_cs == "/DeviceGray":
                                raise Exception("Why are you here !!!")
                            else:
                                r = data[idx_in]
                                g = (
                                    data[idx_in + 1]
                                    if idx_in + 1 < len(data)
                                    else self.raise_exception(
                                        "missing g/m value"
                                    )
                                )
                                b = (
                                    data[idx_in + 2]
                                    if idx_in + 2 < len(data)
                                    else self.raise_exception(
                                        "missing b/y value"
                                    )
                                    # else 0
                                )
                                if color_cs == "/DeviceRGB":
                                    surface_data[idx_out] = b  # Blue
                                    surface_data[idx_out + 1] = g  # Green
                                    surface_data[idx_out + 2] = r  # Red
                                    surface_data[idx_out + 3] = 255  # Alpha
                                elif color_cs == "/DeviceCMYK":
                                    c, m, y = r, g, b
                                    k = (
                                        data[idx_in + 3]
                                        if idx_in + 3 < len(data)
                                        else self.raise_exception(
                                            "missing k value"
                                        )
                                    )

                    else:
                        raise Exception("Exceeded image boundaries !!")
        surface.mark_dirty()

        x, y = self.state.position

        self.ctx.save()
        self.ctx.translate(x, y)
        self.ctx.set_source_surface(surface, 0, 0)
        source = self.ctx.get_source()
        source.set_filter(cairo.FILTER_FAST)

        # Other options:
        # cairo.FILTER_FAST - A high-performance filter
        # cairo.FILTER_GOOD - A reasonable-quality filter
        # cairo.FILTER_BEST - The highest-quality filter
        # cairo.FILTER_NEAREST - Nearest-neighbor filter
        # cairo.FILTER_BILINEAR - Linear interpolation in two dimensions
        # cairo.FILTER_GAUSSIAN - Gaussian convolution filter

        self.ctx.paint()
        self.ctx.restore()
        surface.finish()

        return "", True

    def raise_exception(self, msg):
        raise Exception(msg)

    def sync_matrix(self):
        """Sync Cairo's CTM with the current PDF state matrix"""
        current_matrix = self.state.get_current_matrix()
        # self.ctx.identity_matrix()
        self.ctx.set_matrix(current_matrix)

    def sync_color(
        self,
    ):
        pass

    def execute_command(self, cmd: PdfOperator):
        for ops, sfunc in self.sync_functions_map:
            if cmd.name in ops:
                sfunc()
        func = self.functions_map.get(cmd.name)
        if func:
            return func(cmd)
        else:
            return "", False

    def save_to_png(self, filename: str) -> None:
        """Save the rendered content to a PNG file."""
        if self.surface is None:
            raise ValueError("Renderer is not initialized")
        self.surface.write_to_png(filename)
        # open_image_in_irfan(filename)
        # input("Press Enter to continue...")
        # kill_with_taskkill()
