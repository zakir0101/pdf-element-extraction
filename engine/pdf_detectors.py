# import enum
# from math import isnan
# import time
# import re
# import string
# import sys
# from typing import Tuple
# from .pdf_operator import PdfOperator
# from .engine_state import EngineState
# from .pdf_renderer import BaseRenderer
# import cairo
# import subprocess
# from cairo import Context, Glyph, ImageSurface
# from .pdf_utils import get_segments
# import os
# from fontTools.agl import UV2AGL
# from os.path import sep


from collections import UserList
import enum
from os.path import sep
import cairo
from .pdf_utils import get_next_label, checkIfRomanNumeral, get_segments


class Box:
    def __init__(self):
        self.box = (0, 0, 0, 0)
        pass


class Symbol(Box):
    def __init__(self, ch, x, y, w, h) -> None:
        super().__init__()
        self.ch = ch
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.threshold_y = 0.45 * h
        self.threshold_x = 0.45 * w
        self.box = self.get_box()

        pass

    def __str__(
        self,
    ):
        return f"Smybole({self.ch}, {self.x}, {self.y}, {self.w}, {self.h})"

    def get_box(self):
        """shift the origin of the symbole !! IMPORTANT"""
        return self.x, self.y - self.h, self.x + self.w, self.y

    def is_connected_with(self, s2):
        s2: Symbol = s2
        diff1 = abs(s2.x + s2.w - self.x)
        diff2 = abs(s2.x - self.x + self.w)
        inner_diff = min(diff1, diff2)
        return inner_diff < self.threshold_x or inner_diff < s2.threshold_x


class Sequence(Box):
    def __init__(self, symboles: list[Symbol] | None = None) -> None:
        self.data: list[Symbol] = []
        self.box = (0, 0, 0, 0)
        self.mean = (0, 0)
        self.threshold_y = 20
        self.threshold_x = 20
        if symboles is not None:
            self.data = symboles
            self.__set_box__()
            self.__set_mean__(self.box)

            self.threshold_y = 0.3 * (self.box[-1] - self.box[1])
            self.threshold_x = 0.3 * (self.box[-2] - self.box[0])
        pass

    def __getitem__(self, index) -> Symbol:
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def __str__(self) -> str:
        rep = f"Sequence(lenght={len(self.data)}) =>\n"
        for sym in self.data:
            rep += "   " + str(sym) + "\n"
        return rep  #

    def size(self):
        return self.data.__len__()

    def __set_box__(self):
        # maxx,maxy , maxw,maxh =
        x0, y0, x1, y1 = self.data[0].get_box()
        for d in self.data[1:]:
            nx0, ny0, nx1, ny1 = d.get_box()
            x0 = min(x0, nx0)
            y0 = min(y0, ny0)
            x1 = max(x1, nx1)
            y1 = max(y1, ny1)
        self.box = (x0, y0, x1, y1)

    def __set_mean__(self, box):
        x0, y0, x1, y1 = box
        self.mean = []
        self.mean.append((x0 + x1) / 2)
        self.mean.append((y0 + y1) / 2)

    def row_align_with(self, seq_other):
        seq_other: Sequence = seq_other
        return (
            abs(self.mean[1] - seq_other.mean[1]) < self.threshold_y
            or abs(self.box[-1] - seq_other.box[-1]) < self.threshold_y
        )

    def column_align_with(self, seq_other):
        seq_other: Sequence = seq_other
        return (
            abs(self.mean[0] - seq_other.mean[0]) < self.threshold_x
            or abs(self.box[0] - seq_other.box[0]) < self.threshold_x
        )


class BaseDetector:
    def __init__(self) -> None:
        pass

    # def detect(self, char):
    #     pass


class LineDetector(BaseDetector):
    pass


class ParagraphDetector(BaseDetector):
    pass


class TableDetector(BaseDetector):
    pass


class GraphDetector(BaseDetector):
    pass


class InlineImageDetector(BaseDetector):
    pass


# Content = List[]
UNKNOWN = 0
NUMERIC = 1
ALPHAPET = 2
ROMAN = 3

FIRST_MAP = {NUMERIC: "1", ALPHAPET: "a", ROMAN: "i"}
FACTORS = [1, 2, 5]
LEVEL_QUESTION = 0
LEVEL_PART = 1
LEVEL_SUBPART = 2

TITLE_DICT = ["Question", "PART", "SUBPART"]


class Question(Box):

    TITLE_DICT = ["Question", "PART", "SUBPART"]

    def __init__(
        self,
        label: int | str,
        page: int,
        level: int,
        x: float,
        y: float,
        h: float,
    ):
        super().__init__()
        self.parts: Question = []
        self.label: int | str = label
        self.pages: int = [page]
        self.level: int = level
        self.contents: list[Box] = []
        self.x: int = float(x)
        self.y: int = float(y)
        self.h: int = float(h)

    def __str__(self):
        # in_page = f" In Page {self.pages[0]}" if self.level == 0 else ""
        rep = (
            " " * self.level * 4
            + TITLE_DICT[self.level]
            + " "
            + self.label
            # + in_page
            + f"(x={self.x}, y={self.y}, page={self.pages})"
            + "\n"
        )
        for p in self.parts:
            rep += str(p)
        return rep


def find_questions_part_in_page(q: Question, page: int) -> list[Question]:
    parts: list[Question] = []
    if page not in q.pages:
        return []

    if len(q.pages) == 1:
        parts.append(q)
    else:
        for p in q.parts:
            parts.extend(find_questions_part_in_page(p, page))
    return parts


class QuestionDetector(BaseDetector):
    def __init__(self) -> None:
        super().__init__()
        self.curr_page = -1
        self.height = 100
        self.width = 100
        self.is_first_detection = True
        self.out_surf: cairo.ImageSurface | None = None
        self.out_ctx: cairo.Context | None = None
        self.page_segments: dict[int, list[tuple]] = {}
        self.page_parts: dict[int, list[Question]] = {}
        self.page_heights: dict[int, int] = {}
        self.allowed_skip_chars = [" ", "(", "[", "", ")", "]" "."]
        self.allowed_chars_startup = ["1", "a", "i"]

        self.tolerance = 20
        self.question_list: list[Question] = []

        self.left_most_x: list[int] = [200000, 200000, 200000]
        self.current: list[Question] = [None, None, None]
        self.type: list[int] = [UNKNOWN, UNKNOWN, UNKNOWN]
        pass

    def reset(
        self,
        level: int,
    ):
        self.left_most_x[level:] = [200200] * (3 - level)
        self.type[level:] = [UNKNOWN] * (3 - level)

        if level == 0:
            self.question_list = []
        elif level == 1 and self.current[0]:
            self.current[0].parts = []
        elif level == 2 and self.current[1]:
            self.current[1].parts = []
        # else:
        #     raise Exception

        self.current[level:] = [None] * (3 - level)

    def set_question(self, q: Question, level: int):
        if self.is_first_detection:
            self.is_first_detection = False
            if level > 0:
                self.current[0].pages.append(self.curr_page)
            if level > 1:
                self.current[1].pages.append(self.curr_page)

        old_cur = self.current[level]
        if old_cur and len(old_cur.parts) < 2:
            self.reset(level + 1)
        if level < 2:
            self.current[level + 1 :] = [None] * (3 - level + 1)
            self.type[level + 1 :] = [UNKNOWN] * (3 - level)

        if level == 0:
            self.question_list.append(q)
            self.current[0] = q
        elif level == 1 and self.current[0]:
            self.current[0].parts.append(q)
            self.current[1] = q
        elif level == 2 and self.current[1]:
            self.current[1].parts.append(q)
            self.current[2] = q
        else:
            raise Exception

        n_type = ALPHAPET
        if type(q.label) is int or q.label.isdigit():
            n_type = NUMERIC
        elif checkIfRomanNumeral(q.label):
            n_type = ROMAN
        elif len(q.label) == 1:
            n_type = ALPHAPET
        else:
            raise Exception

        self.type[level] = n_type
        self.left_most_x[level] = q.x

    def get_next_allowed(self, level):
        n_type = self.type[level]
        curr = self.current[level]
        if n_type == UNKNOWN or curr is None:
            if curr is not None:
                raise Exception
            used = None
            if level > 0:
                used = FIRST_MAP[self.type[level - 1]]
            res = [i for i in self.allowed_chars_startup if i != used]
            return res
        return get_next_label(curr.label, n_type)

    def is_char_valid(self, char, level):
        next = self.get_next_allowed(level)
        if type(next) == list:
            return char in next
        next = str(next)
        return next.startswith(char)

    def is_char_skip(self, char, level):
        if level > 0:
            if char in self.current[level - 1].label:
                return True
        return not char or char in self.allowed_skip_chars

    def is_valid_neighbours(self, sym: Symbol, n_sym: Symbol):
        return sym.is_connected_with(n_sym)

    def handle_sequence(self, seq: Sequence, page: int):
        if page != self.curr_page:
            self.curr_page = page
            self.is_first_detection = True
            # self.left_most_x = [1000] * 3
        for level in range(3):
            found = self.__handle_sequence(seq, level)
            if self.current[level] is None:
                break

    def __handle_sequence(self, seq: Sequence, level: int):
        # first_valid : Symbol | None = None
        prev_valid: Symbol | None = None
        is_candidate = False
        char_all = ""
        char, x, y, h, diff = "", 0, 0, 0, 0
        for _, sym in enumerate(seq):
            sym: Symbol = sym
            char = sym.ch
            if prev_valid is None:

                x, y, x1, y1 = sym.get_box()
                h = y1 - y
                self.tolerance = x1 - x
                diff = x - self.left_most_x[level]

                if self.is_char_skip(char, level):
                    continue
                if not self.is_char_valid(char, level):

                    # if level == 2:
                    # print("char ", char, ", is not valid for level", level)
                    is_candidate = False
                    # if diff < -self.tolerance:  # and diff_upper > 0:
                    #     self.reset(level)
                    #     self.left_most_x[level] = x
                    break

                if diff > FACTORS[level] * self.tolerance:
                    # if level == 2:
                    #     print(f"too low value for level {level} , ignoring it")
                    #     print("x=", x, ", diff=", diff, ", char", char)
                    is_candidate = False
                    break

                prev_valid = sym
                is_candidate = True
                char_all = char
                # if level == 2:
                #     print("aim here ,char is ", char)
            else:
                # if level == 2:
                #     print("aim here 2 ,char is ", char)
                if not self.is_valid_neighbours(sym, prev_valid):
                    break
                else:
                    if self.is_char_skip(char, level):
                        continue
                    if not self.is_char_valid(char_all + sym.ch, level):
                        is_candidate = False
                        break

                    prev_valid = sym
                    is_candidate = True
                    char_all += char

        if is_candidate:
            # print("found candidates for level :", level, "and char", char_all)
            # print("diff is ", diff, ", tolerence is ", self.tolerance)
            new_q = Question(char_all, self.curr_page, level, x, y, 2 * h)
            if diff < FACTORS[level] * -self.tolerance:
                # print("resetting to char ", char_all)
                self.reset(level)
            self.set_question(new_q, level)
            return True
        else:
            return False

    def set_height(self, new_width, new_height):
        self.height = new_height
        self.width = new_width

    def calc_page_segments_and_height(
        self, surface: cairo.ImageSurface, page_number: int
    ):
        if not self.question_list:
            raise Exception("no Question Found")
        parts = []
        for i, q in enumerate(self.question_list):
            q: Question = q
            if page_number not in q.pages:
                continue
            parts.extend(find_questions_part_in_page(q, page_number))

        out_height = 0
        self.page_parts[page_number] = parts
        self.page_segments[page_number] = []

        if len(parts) == 0:
            return

        # for i, p in enumerate(parts):
        # y0, d0 = p.y, p.h
        # if i + 1 < len(parts):
        #     n_p = parts[i + 1]
        #     y1 = n_p.y
        # else:
        #     y1 = self.height
        d0 = parts[0].h
        segments = get_segments(surface, 0, self.height, d0, factor=0.5)
        # print(segments)
        # segments = [(y0,h) for y0,h in segments if h]
        self.page_segments[page_number] = segments
        print("number of segs = ", len(segments))
        out_height += sum(seg_h + 2 * d2 for _, seg_h, d2 in segments)
        out_height += 2 * d0
        self.page_heights[page_number] = out_height

    def draw_all_pages_to_single_png(
        self, surf_dict: dict[int, cairo.ImageSurface], pdf_file: str
    ):
        total_height = sum(self.page_heights.values())
        if total_height == 0:
            raise Exception("Total Height = 0")

        out_surf = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.width, int(total_height)
        )
        out_ctx = cairo.Context(out_surf)

        out_ctx.set_source_rgb(1, 1, 1)  # White
        out_ctx.paint()
        out_ctx.set_source_rgb(0, 0, 0)  # Black
        self.dest_y = 0
        self.default_d0 = None
        for page, surf in surf_dict.items():
            d0 = self.__draw_page_content(page, surf, out_ctx)

        exam_name = pdf_file.split(".")[0]
        filename = f"output{sep}{exam_name}.png"
        out_surf = out_surf.create_for_rectangle(
            0, 0, self.width, self.dest_y + 4 * self.default_d0
        )
        out_surf.write_to_png(filename)
        return filename

    def __draw_page_content(
        self, page: int, page_surf: cairo.ImageSurface, out_ctx: cairo.Context
    ):
        if not self.page_segments.get(page) or not self.page_parts.get(page):
            print(f"WARN: skipping page {page}, no Questions found")
            return
        segments = self.page_segments[page]
        parts = self.page_parts[page]

        # d0 = parts[0].h
        for i, (src_y, seg_h, d0) in enumerate(segments):
            if not self.default_d0:
                self.default_d0 = d0
            factor = 2
            if len(segments) == i + 1:
                factor = 4
            # print(src_y, seg_h, d0)
            """subtract 0.20 , why ?? 0.1 for shifting by 0.1 * h0 pixel , because the detecting 
            has some delayed response by this ammount , and +0.1 for padding"""
            y0 = round(src_y - 0.20 * d0)
            """only the 0.2 correspond to the padding , so in practice we shift up by 0.1 and padd by 0.1 from up and down"""
            h0 = round(seg_h + 0.20 * d0)  # + factor * d0
            # print(y0, y1, d0)

            sub = page_surf.create_for_rectangle(0, y0, self.width, h0)
            """Read the doc string below : this is for padding the top most line from above"""
            if self.dest_y == 0:
                self.dest_y = self.dest_y + (1 * d0)
            out_ctx.set_source_surface(sub, 0, self.dest_y)
            out_ctx.paint()
            """this 0.25 is for spacing between lines, it require the surface to
            be paint white at beginning"""
            self.dest_y += h0 + (0.25 * d0)
        return d0

    # def export_whole_surface_to_png(self,pdf_file)


if __name__ == "__main__":
    syms = Sequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
