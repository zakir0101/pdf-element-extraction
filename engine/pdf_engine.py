import os
import cairo
from pypdf.generic import (
    IndirectObject,
    EncodedStreamObject,
    ArrayObject,
    PdfObject,
)
from pypdf import PdfReader, PageObject
import pprint

from engine.pdf_operator import PdfOperator
from engine.pdf_question_renderer import QuestionRenderer
from .pdf_renderer import BaseRenderer
from .pdf_font import PdfFont
from .engine_state import EngineState
from .pdf_stream_parser import PDFStreamParser
from .pdf_detectors import Question, QuestionDetector
from tkinter import Tk, Canvas, PhotoImage, NW, mainloop, BOTH
from os.path import sep
from .pdf_encoding import PdfEncoding as pnc


class PdfEngine:

    def __init__(self, scaling=1, debug=False, clean: bool = True):
        self.scaling = scaling
        self.debug = debug
        self.clean = clean

    def initialize_file(self, pdf_path):
        self.current_stream: str | None = None
        self.pdf_path = pdf_path
        self.reader: PdfReader = PdfReader(pdf_path)
        first_page: PageObject = self.reader.pages[0]
        self.default_width: float = (
            float(first_page.mediabox.width) * self.scaling
        )
        self.default_height: float = (
            float(first_page.mediabox.height) * self.scaling
        )

        self.font_map: dict[str, PdfFont] | None = None

        self.question_detector: QuestionDetector = QuestionDetector()

        self.state: EngineState | None = None
        self.renderer: BaseRenderer | None = None
        self.current_page = 1
        self.pages = self.reader.pages

    def get_color_space_map(self, res):
        colorSpace = {}
        cs = res.get("/ColorSpace")
        if isinstance(cs, IndirectObject):
            cs = self.reader.get_object(cs)
        if not cs:
            return
        for key, value in cs.items():
            # if self.color_map and self.color_map.get(key):
            #     colorSpace[key] = self.color_map[key]

            if isinstance(value, IndirectObject):
                value = self.reader.get_object(value)
            obj = value
            if isinstance(obj, list):
                new_list = []
                for o in obj:
                    if isinstance(o, IndirectObject):
                        o = self.reader.get_object(o)
                    new_list.append(o)

                colorSpace[key] = new_list
                # func = new_list[3]
                # func_data = pnc.bytes_to_string(func.get_data())
                # new_list.append(func_data)
                pass
            else:
                colorSpace[key] = obj

        return colorSpace

    def get_fonts(self, res: dict, depth=0) -> dict:
        fonts = {}
        resources = res
        if resources and resources.get("/Font"):
            for font_name, font_object in resources.get("/Font").items():
                if font_name not in fonts:
                    # if self.font_map and font_name in self.font_map:
                    #     fonts[font_name] = self.font_map[font_name]
                    # else:
                    fonts[font_name] = PdfFont(
                        font_name,
                        self.reader.get_object(font_object),
                        self.reader,
                        self.execute_glyph_stream,
                        depth,
                    )
        return fonts

    def perpare_page_stream(self, page_number: int, rendererClass):

        if page_number < 1 or page_number > len(self.reader.pages):
            raise ValueError("Invalid page number")
        self.current_page = page_number
        page = self.reader.pages[page_number - 1]
        res = page.get("/Resources")
        if isinstance(res, IndirectObject):
            res = self.reader.get_object(res)
        self.res = res
        self.exgtate = self.get_external_g_state(res)
        self.xobject = self.get_x_object(res)
        # print(self.xobject)

        self.default_width = page.mediabox.width
        self.default_height = page.mediabox.height

        self.font_map = self.get_fonts(self.res, 0)
        self.color_map = self.get_color_space_map(self.res)

        self.state = EngineState(
            self.font_map,
            self.color_map,
            self.res,
            self.exgtate,
            self.xobject,
            None,
            self.execute_xobject_stream,
            "MAIN",
            None,
            self.scaling,
            self.default_height,
            self.debug,
        )

        self.renderer = rendererClass(self.state, self.question_detector)
        self.renderer.skip_footer = self.clean

        self.state.draw_image = self.renderer.draw_inline_image

        self.question_detector.set_height(
            int(self.default_width) * self.scaling,
            int(self.default_height) * self.scaling,
        )
        streams_data: list[bytes] = self.get_page_stream_data(page)
        # bytes b"54" and b"03:"
        if b"\xc3\x9f" in streams_data:
            print("ß found")
        for i, b in enumerate(streams_data):
            if b == 54:
                pass
                # print("found", chr(streams_data[i - 1 : i + 2]))
        # print(biggest, chr(biggest))
        if len(streams_data) == 0:
            self.current_stream = pnc.bytes_to_string(
                self.reader.stream.read()
            )
            self.debug_original_stream()
            raise Exception("no data found in this pdf !!!")
        streams_data = pnc.bytes_to_string(streams_data, unicode_excape=True)
        self.current_stream = (
            streams_data  # .encode("latin1").decode( "unicode_escape")
        )
        return self

    def get_page_stream_data(self, page):

        contents = page.get("/Contents")
        # return contents.get_data()
        streams_data = []
        if contents is None:
            raise ValueError("No content found in the page")
        data_count = 0
        if hasattr(contents, "get_object"):
            contents = contents.get_object()
        if isinstance(contents, EncodedStreamObject):
            data = contents.get_data()
            if data:
                streams_data.append(data)
        elif isinstance(contents, ArrayObject):
            for c in contents:
                if hasattr(c, "get_object"):
                    c = c.get_object()
                if isinstance(c, EncodedStreamObject):
                    data = c.get_data()
                    if data:
                        streams_data.append(data)
        return b"".join(streams_data)

    def debug_original_stream(
        self, filename=f"output{sep}original_stream.txt"
    ):
        # print("saving debug info into file")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# FileName: " + os.path.basename(self.pdf_path) + "\n\n")
            f.write("# page number " + str(self.current_page) + "\n\n")
            pprint.pprint(self.pages[self.current_page - 1], f)

            page = self.pages[self.current_page - 1]
            res = self.res

            f.write("\n\n### Resource:\n")
            pprint.pprint(res, f)

            f.write("\n\n### XObject:\n")
            pprint.pprint(self.get_x_object(res), f)
            self.print_fonts(f, res)
            self.print_external_g_state(f, res)
            self.print_color_space(f, res)
            f.write(self.current_stream)
        return self

    def print_color_space(self, f, res):

        colorSpace = self.get_color_space_map(res)
        f.write("\n\n### Color Space\n")
        pprint.pprint(colorSpace, f)

    def print_external_g_state(self, f, res):
        if not self.exgtate:
            self.exgtate = self.get_external_g_state(res)
        f.write("\n\n### External Graphics State\n")
        pprint.pprint(self.exgtate, f)

    def get_external_g_state(self, res):
        exgtate = {}
        ext = res.get("/ExtGState")
        if not ext:
            return {}
        if isinstance(ext, IndirectObject):
            ext = self.reader.get_object(ext)
        for key, value in ext.items():
            obj = self.reader.get_object(value)
            exgtate[key] = obj
        return exgtate

    def get_x_object(self, res):
        x_obj = res.get("/XObject", {})
        if isinstance(x_obj, IndirectObject):
            x_obj = self.reader.get_object(x_obj)

        return x_obj

    def print_fonts(self, f, res):
        reader = self.reader
        f.write("\n\n### Fonts\n")
        output_dict = {}
        for font_name, indir_obj in res.get("/Font").items():
            obj = reader.get_object(indir_obj)
            output_dict[font_name] = {}
            for key, value in obj.items():
                if isinstance(value, list):
                    for v in value:
                        self.update_sub_obj(key, v, output_dict, font_name)
                else:
                    self.update_sub_obj(key, value, output_dict, font_name)
        f.write("\n```python\n")
        pprint.pprint(output_dict, f)
        f.write("\n```\n")

    # def execute_stream(
    #     self,
    #     max_show=100,
    #     stream: str | None = None,
    #     width=None,
    #     height=None,
    # ):
    #     if (
    #         self.state is None
    #         or self.font_map is None
    #         or self.current_stream is None
    #     ):
    #         raise ValueError("Engine not initialized properly")
    #
    #     width = width or self.default_width
    #     height = height or self.default_height
    #     stream = stream or self.current_stream
    #
    #     self.renderer.initialize(
    #         int(width) * self.scaling,
    #         int(height) * self.scaling,
    #         self.current_page,
    #     )
    #     counter = 0
    #
    #     self.parser = PDFStreamParser()
    #     with open(f"output{sep}output.md", "w", encoding="utf-8") as f:
    #         for cmd in self.parser.parse_stream(stream).iterate():
    #             f.write(f"{cmd}\n")
    #
    #             explanation = self.state.execute_command(cmd)
    #
    #             if self.debug and explanation:
    #                 f.write(f"{explanation}\n")
    #             self.renderer.execute_command(cmd)
    #             if cmd.name in ["Tj", "TJ", "'", '"']:
    #                 f.write(f"\n\n")
    #                 counter += 1
    #                 if counter > max_show:
    #                     break
    #     filename = f"output{sep}output.png"
    #     self.renderer.save_to_png(filename)
    #     return filename

    def debug_x_stream(
        self, xres: dict, xstream: str, filename=f"output{sep}xobj_stream.txt"
    ):
        # print("saving debug info into file")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# page number " + str(self.current_page) + "\n\n")
            # pprint.pprint(self.pages[self.current_page - 1], f)

            # page = self.pages[self.current_page - 1]
            # res = self.res
            self.print_fonts(f, xres)
            self.print_external_g_state(f, xres)
            self.print_color_space(f, xres)
            f.write(xstream)

    def execute_glyph_stream(
        self, stream: str, ctx: cairo.Context, char_name: str, font_matrix
    ):
        if self.debug:
            with open(
                f"output{sep}font_stream.txt", "w", encoding="utf-8"
            ) as f:
                f.write("# page number " + str(self.current_page) + "\n\n")
                f.write(stream)

        font_state = EngineState(
            font_map=self.font_map,
            color_map=self.color_map,
            resources=self.res,
            exgstat=None,
            xobj=None,
            initial_state=None,
            execute_xobject_stream=self.execute_xobject_stream,
            stream_name=char_name,
            draw_image=self.renderer.draw_inline_image,
            scale=self.scaling,
            screen_height=self.default_height,
            debug=self.debug,
            depth=self.state.depth,
        )
        m: cairo.Matrix = font_matrix
        cairo.Matrix()
        font_state.set_ctm(
            PdfOperator("cm", [m.xx, m.yx, m.xy, m.yy, m.x0, m.y0])
        )
        old_state = self.renderer.state
        old_ctx = self.renderer.ctx

        self.renderer.state = font_state
        self.renderer.ctx = ctx
        font_state.ctx = ctx

        if stream is None:
            raise ValueError("Font stream is None")

        counter = 0

        x_parser = PDFStreamParser()

        f = self.output_file
        f.write("\n\n\n")
        f.write(f"Font_Stream[{self.state.depth}]: " + "\n")
        f.write("Enter: " + "\n\n\n")
        print("\n\nEnter Font_Stream\n")
        for cmd in x_parser.parse_stream(stream).iterate():
            f.write(f"{cmd}\n")
            explanation, ok = font_state.execute_command(cmd)
            if self.debug and explanation:
                f.write(f"{explanation}\n")
            explanation2, ok2 = self.renderer.execute_command(cmd)
            if self.debug and explanation2:
                f.write(f"{explanation}\n")
            if cmd.name in ["Tj", "TJ", "'", '"']:
                f.write(f"\n\n")
                counter += 1
                # if counter > self.max_show:
                #     break
            if not ok and not ok2:
                print("Font_CMD:", cmd)
                print("Inside Font_State :")
                s = f"{cmd.name} was not handled \n"
                s += f"args : {cmd.args}\n"
                raise Exception("Incomplete Implementaion\n" + s)

        f.write("\n\n")
        f.write(f"Font_Stream[{self.state.depth}]: " + "\n")
        f.write("Exit: " + "\n\n\n")
        self.renderer.state = old_state
        self.renderer.ctx = old_ctx

    def execute_xobject_stream(
        self,
        data_stream: str,
        initial_state: dict,
        xres: dict,
        depth: int,
        stream_name,
    ):

        x_stream = data_stream
        if self.debug:
            self.debug_x_stream(xres, x_stream)
        x_font_map = self.get_fonts(xres, depth)
        x_state: EngineState | None = None
        x_exgtate = self.get_external_g_state(xres)
        x_xobject = self.get_x_object(xres)

        x_state = EngineState(
            x_font_map,
            self.color_map,
            xres,
            x_exgtate,
            x_xobject,
            initial_state,
            self.execute_xobject_stream,
            stream_name,
            self.renderer.draw_inline_image,
            self.scaling,
            self.default_height,
            self.debug,
            depth,
        )
        old_state = self.renderer.state
        self.renderer.state = x_state

        if x_font_map is None or x_stream is None:
            raise ValueError("Engine not initialized properly")

        x_state.ctx = self.renderer.ctx
        counter = 0

        x_parser = PDFStreamParser()

        f = self.output_file
        f.write("\n\n\n")
        f.write(f"X_Stream[{depth}]: " + "\n")
        f.write("Enter: " + "\n\n\n")
        # print("\n\nEnter X_FORM\n")
        for cmd in x_parser.parse_stream(x_stream).iterate():
            f.write(f"{cmd}\n")
            explanation, ok = x_state.execute_command(cmd)
            if self.debug and explanation:
                f.write(f"{explanation}\n")
            explanation2, ok2 = self.renderer.execute_command(cmd)

            if self.debug and explanation2:
                f.write(f"{explanation}\n")
            if cmd.name in ["Tj", "TJ", "'", '"']:
                f.write(f"\n\n")
                counter += 1
                if counter > self.max_show:
                    break
            if not ok and not ok2:

                print("X_CMD:", cmd)
                print("Inside XFORM :")
                s = f"{cmd.name} was not handled \n"
                s += f"args : {cmd.args}\n"
                raise Exception("Incomplete Implementaion\n" + s)

        f.write("\n\n")
        f.write(f"X_Stream[{depth}]: " + "\n")
        f.write("Exit: " + "\n\n\n")
        # print("\nExit X_FORM\n\n")
        self.renderer.state = old_state

    def execute_stream_extract_question(
        self,
        max_show=10000,
        mode=0,
        stream: str | None = None,
        width=None,
        height=None,
    ) -> int:
        if (
            self.state is None
            or self.font_map is None
            or self.current_stream is None
        ):
            raise ValueError("Engine not initialized properly")
        self.max_show = max_show
        width = width or self.default_width
        height = height or self.default_height
        stream = stream or self.current_stream

        renderer: QuestionRenderer = self.renderer
        renderer.mode = mode
        self.renderer.initialize(
            int(width) * self.scaling,
            int(height) * self.scaling,
            self.current_page,
        )
        self.state.ctx = self.renderer.ctx
        counter = 0

        self.parser = PDFStreamParser()
        f = open(f"output{sep}output.md", "w", encoding="utf-8")
        self.renderer.output = f
        self.output_file = f
        f.write("FILE: " + os.path.basename(self.pdf_path) + "\n")
        f.write("PAGE: " + str(self.current_page) + "\n\n\n")
        for cmd in self.parser.parse_stream(stream).iterate():
            f.write(f"{cmd}\n")
            explanation, ok = self.state.execute_command(cmd)

            if self.debug and explanation:
                f.write(f"{explanation}\n")
            explanation2, ok2 = renderer.execute_command(cmd)
            if self.debug and explanation2:
                f.write(f"{explanation2}\n")
            if cmd.name in ["Tj", "TJ", "'", '"']:

                f.write(f"counter={counter}\n\n")
                counter += 1
                if counter > max_show:
                    break
            if not ok and not ok2:

                print("CMD:", cmd)
                s = f"{cmd.name} was not handled \n"
                s += f"args : {cmd.args}\n"
                raise Exception("Incomplete Implementaion\n" + s)

        f.flush()
        f.close()

    def show_image(self, file_path):
        root = Tk("pdf_viewer")
        # create a containter for canvas using pytikner class
        # container = Frame(root)

        canvas = Canvas(
            root, width=self.default_width, height=self.default_height
        )  # ,

        canvas.pack(fill=BOTH, expand=True, padx=40, pady=0)
        # padx=50, pady=0,
        img = PhotoImage(file=file_path)
        # img = img.zoom(-int(self.scale),-int(self.scale))
        canvas.create_image(0, 0, anchor=NW, image=img)

        mainloop()

    def update_sub_obj(self, key, value, output_dict, font_name):
        if isinstance(value, IndirectObject):
            new_value = self.reader.get_object(value)
            output_dict[font_name][key] = {}
            for key2, value2 in new_value.items():
                if isinstance(value2, IndirectObject):
                    # print("Indirect Object")
                    output_dict[font_name][key][key2] = self.reader.get_object(
                        value2
                    )
                else:
                    output_dict[font_name][key][key2] = value2
        else:
            output_dict[font_name][key] = value


if __name__ == "__main__":
    pdf_path = "9702_m23_qp_12.pdf"
    pdf_engine = PdfEngine(pdf_path)
    data = pdf_engine.perpare_page_stream(3)
    # pdf_engine.execute_stream(stream)
    pass
