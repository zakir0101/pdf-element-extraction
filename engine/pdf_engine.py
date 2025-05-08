import os
from PyPDF2.generic import (
    IndirectObject,
    EncodedStreamObject,
    ArrayObject,
)
from PyPDF2 import PdfReader, PageObject
import pprint

from engine.pdf_question_renderer import QuestionRenderer
from .pdf_renderer import BaseRenderer
from .pdf_font import PdfFont
from .engine_state import EngineState
from .pdf_stream_parser import PDFStreamParser
from .pdf_detectors import Question, QuestionDetector
from tkinter import Tk, Canvas, PhotoImage, NW, mainloop, BOTH
from os.path import sep


class PdfEngine:

    def __init__(self, pdf_path, scaling=1, debug=False):
        self.pdf_path = pdf_path
        self.scaling = scaling
        self.debug = debug
        self.reader: PdfReader = PdfReader(pdf_path)

        first_page: PageObject = self.reader.pages[0]
        self.default_width: float = float(first_page.mediabox.width) * scaling
        self.default_height: float = (
            float(first_page.mediabox.height) * scaling
        )
        self.current_stream: str | None = None

        self.pages = self.reader.pages
        self.font_map: dict[str, PdfFont] | None = None
        self.scale = 1
        self.parser = PDFStreamParser()

        self.state: EngineState | None = None
        self.renderer: BaseRenderer | None = None
        self.current_page = 1
        self.question_detector: QuestionDetector = QuestionDetector()

    def get_fonts(self, reader: PdfReader, page_number: int = 0) -> dict:
        fonts = {}
        resources = self.pages[page_number - 1].get("/Resources")
        resources = (
            reader.get_object(resources)
            if isinstance(resources, IndirectObject)
            else resources
        )
        if resources and resources.get("/Font"):
            # fonts.update(self.get_fonts_from_resources(resources))
            for font_name, font_object in resources.get("/Font").items():
                if font_name not in fonts:
                    fonts[font_name] = PdfFont(
                        font_name, reader.get_object(font_object), reader
                    )
        return fonts

    def get_page_stream(self, page_number: int, rendererClass):

        if page_number < 1 or page_number > len(self.reader.pages):
            raise ValueError("Invalid page number")
        self.current_page = page_number
        page = self.reader.pages[page_number - 1]
        self.default_width = page.mediabox.width
        self.default_height = page.mediabox.height

        self.font_map = self.get_fonts(self.reader, page_number)
        self.state = EngineState(
            self.font_map, self.scaling, self.default_height, self.debug
        )

        self.renderer = rendererClass(self.state, self.question_detector)

        contents = page.get_contents()

        streams_data = []
        if contents is None:
            raise ValueError("No content found in the page")

        # Resolve if indirect
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

        streams_data = [
            data.decode("latin1", "replace") for data in streams_data
        ]
        self.current_stream = "\n".join(streams_data)
        return self

    def debug_original_stream(
        self, filename=f"output{sep}original_stream.txt"
    ):
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# page number " + str(self.current_page) + "\n\n")
            pprint.pprint(self.pages[self.current_page - 1], f)

            page = self.pages[self.current_page - 1]
            res = page.get("/Resources")
            if isinstance(res, IndirectObject):
                res = self.reader.get_object(res)
            self.print_fonts(f, res)
            self.print_external_g_state(f, res)
            self.print_color_space(f, res)
            f.write(self.current_stream)
        return self

    def print_color_space(self, f, res):

        colorSpace = {}
        cs = res.get("/ColorSpace")
        if isinstance(cs, IndirectObject):
            cs = self.reader.get_object(cs)
        if not cs:
            return
        for key, value in cs.items():
            obj = self.reader.get_object(value)
            colorSpace[key] = obj

        f.write("\n\n### Color Space\n")
        pprint.pprint(colorSpace, f)

    def print_external_g_state(self, f, res):
        exgtate = {}
        ext = res.get("/ExtGState")
        if isinstance(ext, IndirectObject):
            ext = self.reader.get_object(ext)
        for key, value in ext.items():
            obj = self.reader.get_object(value)
            exgtate[key] = obj

        f.write("\n\n### External Graphics State\n")
        pprint.pprint(exgtate, f)

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

    def execute_stream(
        self,
        max_show=100,
        stream: str | None = None,
        width=None,
        height=None,
    ):
        if (
            self.state is None
            or self.font_map is None
            or self.current_stream is None
        ):
            raise ValueError("Engine not initialized properly")

        width = width or self.default_width
        height = height or self.default_height
        stream = stream or self.current_stream

        self.renderer.initialize(
            int(width) * self.scaling,
            int(height) * self.scaling,
            self.current_page,
        )
        counter = 0
        with open(f"output{sep}output.md", "w", encoding="utf-8") as f:
            for cmd in self.parser.parse_stream(stream).iterate():
                f.write(f"{cmd}\n")
                explanation = self.state.execute_command(cmd)
                if self.debug and explanation:
                    f.write(f"{explanation}\n")
                self.renderer.execute_command(cmd)
                if cmd.name in ["Tj", "TJ", "'", '"']:
                    f.write(f"\n\n")
                    counter += 1
                    if counter > max_show:
                        break
        self.renderer.save_to_png(f"output{sep}output.png")
        # self.show_image("output\output.png")

    def execute_stream_extract_question(
        self,
        max_show=100,
        expected_next=1,
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

        width = width or self.default_width
        height = height or self.default_height
        stream = stream or self.current_stream

        renderer: QuestionRenderer = self.renderer
        self.renderer.initialize(
            int(width) * self.scaling,
            int(height) * self.scaling,
            self.current_page,
        )
        counter = 0
        for cmd in self.parser.parse_stream(stream).iterate():
            explanation = self.state.execute_command(cmd)
            renderer.execute_command(cmd)
        # self.renderer.save_to_png(f"output{sep}output.png")
        # renderer.save_questions_to_pngs(os.path.basename(self.pdf_path))
        return expected_next
        # self.renderer.start_partioning()
        # for cmd in self.parser.parse_stream(stream).iterate():
        #     explanation = self.state.execute_command(cmd)
        #     renderer.execute_command(cmd)
        # return expected_next

        # self.show_image("output\output.png")

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
    data = pdf_engine.get_page_stream(3)
    # pdf_engine.execute_stream(stream)
    pass
