import os
from pprint import pprint
from typing import override
import cairo
from .core_models import Box, SurfaceGapsSegments
from engine.pdf_utils import crop_image_surface


class QuestionBase(Box):

    TITLE_DICT = ["Question", "PART", "SUBPART"]

    def __init__(
        self,
        label: int | str,
        pages: int | list[int],
        level: int,
        x: float,
        y: float,
        w: float,
        page_height: float,
        line_h: float,
    ):
        super().__init__(x, y, w, page_height)
        self.parts: QuestionBase = []
        self.label: int | str = label
        if isinstance(pages, int):
            self.pages: int = [pages]
        else:
            self.pages: int = pages

        self.level: int = level
        self.contents: list[Box] = []
        # self.x: float = float(x)
        # self.y: float = float(y)
        self.y1: float | None = None
        self.line_height: int = float(line_h)

    def __str__(self):
        # in_page = f" In Page {self.pages[0]}" if self.level == 0 else ""
        rep = (
            " " * self.level * 4
            + self.TITLE_DICT[self.level]
            + " "
            + self.label
            # + in_page
            + f"(x={self.x}, y={self.y}, y1={self.y1 or "None"}, page={self.pages})"
            + "\n"
        )
        for p in self.parts:
            rep += str(p)
        return rep

    def __to_dict__(self):
        if len(self.parts) > 1:
            part_dict = ([p.__to_dict__() for p in self.parts],)
        else:
            part_dict = []
        return {
            "label": self.label,
            "pages": self.pages,
            "x": self.x,
            "y": self.y,
            "y1": self.y1,
            "h": self.line_height,
            "parts": part_dict,
        }

    @classmethod
    def __from_dict__(self, qd: dict, shallow: bool, level=0):
        q = QuestionBase(
            qd["label"], qd["pages"], level, qd["x"], qd["y"], qd["h"]
        )
        q.y1 = qd["y1"]
        if shallow:
            return q
        q.parts = []
        for p in qd["parts"]:
            q.parts.append(
                QuestionBase.__from_dict__(p, shallow=False, level=level + 1)
            )
        return q

    def get_title(self):
        return (
            " " * self.level * 4
            + self.TITLE_DICT[self.level]
            + " "
            + self.label
            # + in_page
            + f"(x={self.x}, y={self.y}, y1={self.y1 or 'None'}, page={self.pages})"
            + ""
        )


class Question(QuestionBase):
    # TODO:
    """should include additional field like, question_id,category ,subject,exams ..etc"""

    def __init__(
        self,
        id: str,
        exam: str,
        label: int | str,
        pages: int | list[int],
        level: int,
        parts: list[QuestionBase],
        contents: list[Box],
        x: float,
        y: float,
        w: float,
        page_height: float,
        y1: float,
        line_height: float,
    ) -> None:
        heigh = self.calculate_height(y, y1, pages, page_height)
        super().__init__(label, pages, level, x, y, w, y1 - y, line_height)
        self.parts = parts
        self.contents = contents
        self.y1 = y1
        self.id = id
        if isinstance(label, str) and not label.isdigit():
            raise Exception(
                "only top level BaseQuestion can form a question object"
            )
        self.number = int(label)
        self.exam = exam
        pass

    def calculate_height(self, y0, y1, pages, page_height):
        if len(pages) == 0:
            raise
        elif len(pages) == 1:
            return y1 - y0
        else:
            height1 = page_height - y0
            height2 = y1
            height_middle = (len(pages) - 2) * page_height
            return height1 + height2 + height_middle

    @classmethod
    def from_base(cls, q: QuestionBase, exam_path_or_filename: str, q_nr: int):
        exam = os.path.basename(exam_path_or_filename)
        exam_id = exam.split(".")[0]
        q_id = f"{exam_id}_{str(q_nr)}"
        return Question(
            q_id,
            exam_id,
            q.label,
            q.pages,
            q.level,
            q.parts,
            q.contents,
            q.x,
            q.y,
            q.w,
            q.h,
            q.y1,
            q.line_height,
        )

    def draw_question_on_image_surface(
        self,
        page_segments_dict: dict[int, SurfaceGapsSegments],
        header_y,
        footer_y,
    ):
        """render the question on cairo image surface"""
        out_ctx = None
        out_surf = None

        total_height = sum([s.net_height for s in page_segments_dict.values()])
        if total_height <= 0:
            raise Exception("Total Height = 0")

        self.current_y = 0
        for i, page in enumerate(self.pages):
            # TODO:
            print([k for k in page_segments_dict.keys()])
            page_seg = page_segments_dict[page]

            page_surf = page_seg.surface
            if i == 0:
                # assume all have the same width
                out_ctx, out_surf = self.create_output_surface(
                    page_surf.get_width(), total_height
                )
                out_ctx.save()
                out_ctx.move_to(self.line_height * 4, self.line_height * 2)
                out_ctx.show_text(f"<Question {self.number}>")
                out_ctx.restore()

            q_segments: list[Box] = page_seg.filter_question_segments(
                self.y, self.y1, self.pages, page
            )

            seg_remove = []
            for j in range(len(q_segments)):
                # print("len = ", len(q_segments), "j=", j)
                b = q_segments[j]
                (b.y < header_y) and seg_remove.append(b)
                ((b.y + b.h) > footer_y) and seg_remove.append(b)
            for seg in seg_remove:
                q_segments.remove(seg)

            if not q_segments or len(q_segments) == 0:
                print(
                    f"WARN: skipping page {page}, no Segments found for question {self.__str__()}"
                )
                continue
            # f_seg = q_segments[0]
            # l_seg = q_segments[-1]
            # q_height = l_seg.y + l_seg.h - f_seg.y
            # q_segments = [Box(f_seg.x, f_seg.y, f_seg.w, q_height)]
            self.current_y = page_seg.clip_segments_from_surface_into_contex(
                out_ctx, self.current_y, q_segments
            )

        if self.current_y == 0:
            print(self.__str__())
            print("all Segs")
            for seg in page_seg:
                print(seg)
            raise Exception("no heigth for question")

        padding = 2 * (self.line_height)
        return crop_image_surface(out_surf, 0, self.current_y, padding)

    def create_output_surface(self, width: int, total_height: int):
        out_surf = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, width, int(total_height)
        )
        out_ctx = cairo.Context(out_surf)
        out_ctx.set_source_rgb(1, 1, 1)  # White
        out_ctx.paint()
        out_ctx.set_source_rgb(0, 0, 0)  # Black
        return out_ctx, out_surf
