import re
import string

from engine.create_cairo_font import open_image_in_irfan
from .pdf_operator import PdfOperator
from .engine_state import EngineState
import cairo
import subprocess
from cairo import Context, ImageSurface
import os
from .pdf_detectors import Sequence, Symbol, BaseDetector

SEP = os.path.sep


class BaseRenderer:
    def __init__(
        self, state: EngineState, main_detector: BaseDetector
    ) -> None:
        self.state: EngineState = state
        self.default_char_width = 10
        self.functions_map = {
            "TJ": self.draw_string_array,
            "Tj": self.draw_string,
            "'": self.draw_string,
            '"': self.draw_string,
            "m": self.move_line_to,
            "l": self.draw_line_to,
            "re": self.draw_rectangle,
            "f": self.fill_path,
            "S": self.stroke_path,
            "EI": self.draw_inline_image,
            "W": self.draw_clip,
            "n": self.end_path,
            "q": self.save_state,
            "Q": self.restore_state,
            # "EI": self.test_surface_paint,
            # Existing operators...
            "h": self.close_path,
            "c": self.curve_to,
            "k": self.set_cmyk_color,
            "ET": self.end_text,
        }

        self.surface: ImageSurface | None = None
        self.ctx: Context | None = None
        self.skip_footer = True
        self.page_number = -1
        self.main_detector: BaseDetector = main_detector

    def initialize(self, width: int, height: int, page: int) -> None:
        """Initialize the Cairo surface and context."""
        self.width = width
        self.height = height
        self.page_number = page
        self.footer_y = height * 0.95
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

    def curve_to(self, cmd: PdfOperator):
        """Draw a cubic Bezier curve"""
        x1, y1, x2, y2, x3, y3 = cmd.args
        self.ctx.curve_to(x1, y1, x2, y2, x3, y3)
        self.state.position = [x3, y3]

    def set_cmyk_color(self, cmd: PdfOperator):
        """Set CMYK color"""
        # Color conversion is handled by EngineState
        # Just need to update the context's color
        self.ctx.set_source_rgb(*self.state.fill_color)

    def end_text(self, _: PdfOperator):
        """End text object"""
        # Most of the work is handled by EngineState
        pass

    def draw_clip(self, _: PdfOperator):
        # W operator - Set clipping path
        # Even if we don't fully implement shape rendering,
        # we should at least acknowledge the clipping path
        self.ctx.clip()
        self.ctx.new_path()

    def end_path(self, _: PdfOperator):
        # n operator - End path without filling/stroking
        self.ctx.new_path()

    def save_state(self, _: PdfOperator):
        # q operator
        # handled by EngineState
        self.ctx.save()
        pass

    def restore_state(self, _: PdfOperator):
        # Q operator
        # handled by EngineState
        self.ctx.restore()
        # self.sync_matrix()
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
        self.draw_string_array(cmd, is_single=True)

    def count_dots(self, char_seq):
        dot = "."
        return len([sym for sym in char_seq if dot in sym.ch])

    def should_skip_sequence(self, char_seq):
        if len(char_seq) == 0:
            return True
        if self.skip_footer and char_seq[0].y >= self.footer_y:
            return True

    def draw_string_array(self, cmd: PdfOperator, is_single=False):
        glyph_array, char_seq, update_text_position = self.get_glyph_array(
            cmd, is_single
        )
        char_seq: Sequence = char_seq
        if self.should_skip_sequence(char_seq):
            return
        if self.count_dots(char_seq) < 20:
            self.draw_glyph_array(glyph_array)
        update_text_position()

    def get_glyph_array(self, cmd: PdfOperator, is_single=False):
        if is_single:
            text_array = [cmd.args[0]]
        else:
            text_array = cmd.args[0]

        state = self.state
        x, y = state.text_position
        font_size = state.font_size

        char_regex = r"(?:(?:^|[^\\])\\(?P<symbol>\d{3}))|(?P<char>.)"

        font = self.state.font

        cairo_font_face = None
        try:
            cairo_font_face = font.get_cairo_font_face()
        except Exception as e:
            pass
            print(f"Error loading embedded font face: {e}")

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
                for word in re.split(
                    r"([ ]+)", element, flags=re.DOTALL | re.MULTILINE
                ):
                    if word.isspace():
                        x += w_spacing
                    for char_or in re.finditer(char_regex, word):
                        glyph_id, char_width, char = (
                            self.get_glyph_id_for_char(char_or)
                        )
                        if glyph_id is None:
                            continue
                        glyph_obj = cairo.Glyph(glyph_id, x, y)
                        glyph_array.append(glyph_obj)
                        x0, y0 = m_c.transform_point(x, y)
                        char_height = self.ctx.glyph_extents(
                            [glyph_obj]
                        ).y_bearing
                        w, h = m_c.transform_distance(char_width, char_height)
                        char_array.append(Symbol(char, x0, y0, w, h))
                        x += char_width + c_spacing

            else:
                raise ValueError("Invalid text element")

        def update_on_finish():
            if is_single:
                self.state.text_position = [x, y]

        return glyph_array, Sequence(char_array), update_on_finish

    def get_glyph_id_for_char(self, char_or):
        font = self.state.font
        char = char_or.group("char")
        symbol = char_or.group("symbol")
        if char:
            if not font.is_composite:
                char_width = font.get_char_width(char)
                glyph_id = font.char_to_gid.get(char)

                if glyph_id is None:
                    if char == "p":
                        print("correcting p")
                        glyph_id = font.symbol_to_gid.get("pi")
                        char = "pi"
            else:
                glyph_id = ord(char)
                char_width = font.widths[glyph_id]

        elif symbol:
            char_code, char_width = font.get_char_code(symbol)
            symbol = font.diff_map.get(char_code, "").replace("/", "")
            if not symbol:
                symbol = font.get_symbol_name_from_char_code(char_code)
            glyph_id = font.symbol_to_gid.get(symbol)
            char = symbol

        char_width = self.state.convert_em_to_ts(char_width)
        return glyph_id, char_width, char

    def draw_glyph_array(self, glyph_array):
        self.ctx.save()
        try:
            # self.ctx.set_font_size(self.state.font_size)
            # self.ctx.translate(0, 0)
            # self.ctx.scale(1, 1)
            self.ctx.move_to(0, 0)
            self.ctx.show_glyphs(glyph_array)
        except:
            print("error")
            raise ValueError(f"ERROR while drawing Glyph array")
        self.ctx.restore()

    def clean_text(self, text: str):
        text = text.replace("\\(", "(").replace("\\)", ")")
        return text

    def stroke_path(self, _: PdfOperator) -> None:
        """Draw a line using Cairo."""
        if self.ctx is None:
            raise ValueError("Renderer is not initialized")
        self.ctx.set_line_width(self.state.line_width)

        # set gray color
        self.ctx.set_source_rgb(*self.state.stroke_color)
        self.ctx.set_dash(self.state.dash_pattern, 0)
        self.ctx.set_line_cap(self.state.line_cap)
        self.ctx.set_line_join(self.state.line_join)
        self.ctx.set_miter_limit(self.state.miter_limit)
        self.ctx.stroke()
        # self.ctx.stroke_preserve()

    def move_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.move_to(x, y)
        self.state.position = [x, x]

    def draw_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.line_to(x, y)
        self.state.position = [x, y]

    def draw_rectangle(self, cmd: PdfOperator):
        x, y, width, height = cmd.args
        self.ctx.rectangle(x, y, width, height)

    def fill_path(self, cmd: PdfOperator) -> None:
        """Fill the current path using Cairo."""
        fill_rule = cairo.FILL_RULE_WINDING
        self.ctx.set_fill_rule(fill_rule)
        self.ctx.set_source_rgb(*self.state.fill_color)
        self.ctx.fill()

    PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "

    def hex_escape(self, s):
        return "".join(
            c if c in BaseRenderer.PRINTABLE else r"\x{0:02x}".format(ord(c))
            for c in s
        )

    def draw_inline_image(self, cmd: PdfOperator):
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
            r, g, b = [int(c * 255) for c in fill_color]

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
                        if bits_per_component <= 8:
                            pixel = data[idx_in]
                            pixel = (pixel * 255) // (
                                (1 << bits_per_component) - 1
                            )
                            # Grayscale
                            surface_data[idx_out] = pixel  # Blue
                            surface_data[idx_out + 1] = pixel  # Green
                            surface_data[idx_out + 2] = pixel  # Red
                            surface_data[idx_out + 3] = 255  # Alpha
                        else:
                            # RGB data
                            r = data[idx_in]
                            g = (
                                data[idx_in + 1]
                                if idx_in + 1 < len(data)
                                else 0
                            )
                            b = (
                                data[idx_in + 2]
                                if idx_in + 2 < len(data)
                                else 0
                            )
                            surface_data[idx_out] = b  # Blue
                            surface_data[idx_out + 1] = g  # Green
                            surface_data[idx_out + 2] = r  # Red
                            surface_data[idx_out + 3] = 255  # Alpha
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

    def sync_matrix(self):
        """Sync Cairo's CTM with the current PDF state matrix"""
        current_matrix = self.state.get_current_matrix()
        # self.ctx.identity_matrix()
        self.ctx.set_matrix(current_matrix)

    def execute_command(self, cmd: PdfOperator):

        if cmd.name in self.state.do_sync_after:
            # print("syncing matrix, after ", cmd.name)
            self.sync_matrix()
        func = self.functions_map.get(cmd.name)
        if func:
            func(cmd)

    def kill_with_taskkill(self):
        """Use Windows’ native taskkill (works from Windows or WSL)."""
        TARGET = "i_view64.exe"
        cmd = ["taskkill.exe", "/IM", TARGET, "/F"]
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def open_image_in_irfan(self, img_path):
        c_prefix = "C:" if os.name == "nt" else "/mnt/c"
        png_full_path = "\\\\wsl.localhost\\Ubuntu" + os.path.abspath(img_path)
        if os.name != "nt":  # Windows
            png_full_path = png_full_path.replace("/", "\\")
        subprocess.Popen(
            args=[
                f"{c_prefix}{SEP}Program Files{SEP}IrfanView{SEP}i_view64.exe",
                png_full_path,
            ]
        )

    def save_to_png(self, filename: str) -> None:
        """Save the rendered content to a PNG file."""
        self.kill_with_taskkill()
        print("saving image")
        if self.surface is None:
            raise ValueError("Renderer is not initialized")
        self.surface.write_to_png(filename)
        open_image_in_irfan(filename)
        input("Press Enter to continue...")
        self.kill_with_taskkill()

    # regex = r"(?:^|[^\\])\\(?P<symbol>\d{3})"
