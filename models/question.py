import cairo
from .core_models import Box, SurfaceGapsSegments
from engine.pdf_utils import __crop_image_surface


class QuestionBase(Box):

    TITLE_DICT = ["Question", "PART", "SUBPART"]

    def __init__(
        self,
        label: int | str,
        page: int | list[int],
        level: int,
        x: float,
        y: float,
        h: float,
    ):
        super().__init__()
        self.parts: QuestionBase = []
        self.label: int | str = label
        if isinstance(page, int):
            self.pages: int = [page]
        else:
            self.pages: int = page

        self.level: int = level
        self.contents: list[Box] = []
        self.x: float = float(x)
        self.y: float = float(y)
        self.y1: float | None = None
        self.line_height: int = float(h)

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
        page: int | list[int],
        level: int,
        x: float,
        y: float,
        h: float,
        y1: float,
    ) -> None:
        super().__init__(label, page, level, x, y, h)
        self.y1 = y1
        self.id = id
        if isinstance(label, str) and not label.isdigit():
            raise Exception(
                "only top level BaseQuestion can form a question object"
            )
        self.number = int(label)
        self.exam = exam
        pass

    def draw_question_on_image_surface(
        self,
        page_segments_dict: dict[int, SurfaceGapsSegments],
    ):
        """render the question on cairo image surface"""
        out_ctx = None
        out_surf = None
        self.dest_y = 0
        # self.default_line_height = self .line

        total_height = sum([s.net_height for s in page_segments_dict.values()])
        if total_height <= 0:
            raise Exception("Total Height = 0")
        for i, page in enumerate(self.pages):

            # TODO:
            page_seg = page_segments_dict[page]
            page_surf = page_seg.surface
            if i == 0:
                # assume all have the same width
                out_ctx, out_surf = self.create_output_surface(
                    page_surf.get_width(), total_height
                )

            q_segments = page_seg.filter_question_segments(
                self.y, self.y1, self.pages, page
            )

            if not q_segments or len(q_segments) == 0:
                print(
                    f"WARN: skipping page {page}, no Segments found for question {self.__str__()}"
                )
                continue

            self.dest_y = page_seg.__clip_segments_from_surface_into_contex(
                out_ctx, self.dest_y, q_segments
            )

        if self.dest_y == 0:
            raise Exception("no heigth for question", self.__str__())

        padding = 2 * (self.line_height)
        return __crop_image_surface(out_surf, 0, self.dest_y, padding)

    def create_output_surface(self, width: int, total_height: int):
        out_surf = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, width, int(total_height)
        )
        out_ctx = cairo.Context(out_surf)
        out_ctx.set_source_rgb(1, 1, 1)  # White
        out_ctx.paint()
        out_ctx.set_source_rgb(0, 0, 0)  # Black
        return out_ctx, out_surf
