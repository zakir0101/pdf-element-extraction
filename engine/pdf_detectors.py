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
import os
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
        return f"Smybole({self.ch}, x={self.x}, y={self.y}, w={self.w}, h={self.h})"

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

    def get_text(self) -> str:
        rep = ""
        for sym in self.data:
            rep += sym.ch
        return (
            f"Sequence(lenght={len(self.data)}, content={rep}, box={self.box})"
        )

    def size(self):
        return self.data.__len__()

    def __set_box__(self):
        # maxx,maxy , maxw,maxh =
        if len(self.box) == 0:
            return
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

FIRST_MAP = {UNKNOWN: "0", NUMERIC: "1", ALPHAPET: "a", ROMAN: "i"}
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
        self.x: float = float(x)
        self.y: float = float(y)
        self.y1: float | None = None
        self.h: int = float(h)

    def __str__(self):
        # in_page = f" In Page {self.pages[0]}" if self.level == 0 else ""
        rep = (
            " " * self.level * 4
            + TITLE_DICT[self.level]
            + " "
            + self.label
            # + in_page
            + f"(x={self.x}, y={self.y}, y1={self.y1 or "None"}, page={self.pages})"
            + "\n"
        )
        for p in self.parts:
            rep += str(p)
        return rep

    def get_title(self):
        return (
            " " * self.level * 4
            + TITLE_DICT[self.level]
            + " "
            + self.label
            # + in_page
            + f"(x={self.x}, y={self.y}, y1={self.y1 or 'None'}, page={self.pages})"
            + ""
        )


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


file = open(f"output{sep}detector_output.md", "w", encoding="utf-8")


def print(*args):
    args = [str(a) for a in args]
    file.write("".join(args) + "\n")
    file.flush()


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
        self.page_parts_per_question: dict[int, dict[int, Question]] = {}
        self.page_heights: dict[int, int] = {}
        self.allowed_skip_chars = [" ", "(", "[", "", ")", "]" "."]
        self.allowed_chars_startup = ["1", "a", "i"]

        self.tolerance = 20
        self.question_list: list[Question] = []

        self.left_most_x: list[int] = [0] * 3
        self.current: list[Question] = [None, None, None]
        self.type: list[int] = [UNKNOWN, UNKNOWN, UNKNOWN]
        pass

    def set_height(self, new_width, new_height):
        self.height = new_height
        self.width = new_width
        if len(self.question_list) == 0:
            self.reset_left_most()

    def reset_left_most(self, level=None):
        if level:
            self.left_most_x[level:] = [self.width / 3] * (3 - level)
        else:
            self.left_most_x = [self.width / 3] * 3

    def reset_types(self, level):
        self.type[level:] = [UNKNOWN] * (3 - level)

    def reset_current(self, level):
        self.current[level:] = [None] * (3 - level)

    def reset(
        self,
        level: int,
    ):
        self.reset_left_most(level)
        self.reset_types(level)

        if level == 0:
            self.question_list = []
        elif level == 1 and self.current[0]:
            self.current[0].parts = []
        elif level == 2 and self.current[1]:
            self.current[1].parts = []
        # else:
        #     raise Exception

        self.current[level:] = [None] * (3 - level)
        self.reset_current(level)

    def replace_question(self, q: Question, level: int):
        old_curr = self.current[level]
        if old_curr and len(old_curr.parts) > 1:
            print(
                "Can not replace old question because it already has detected 2+ parts"
            )
            return
        elif (
            old_curr
            and len(old_curr.parts) > 0
            and len(old_curr.parts[0].parts) > 1
        ):
            print(
                "Can not replace old question because it already has detected a part with 2+ sub-parts"
            )
            return
        elif not old_curr:
            self.set_question(q, level)
            return

        print("trying to replace old question")

        self.set_page_number_for_first_detection(level)
        if level < 2:
            self.reset(level + 1)
        # if level < 2:
        #     self.current[level + 1 :] = [None] * (3 - level + 1)
        #     self.type[level + 1 :] = [UNKNOWN] * (3 - level)
        print(q)
        print([str(f) for f in self.question_list])

        if level == 0:
            self.question_list[-1] = q

        elif level == 1 and self.current[0]:
            self.current[0].parts[-1] = q
        elif level == 2 and self.current[1]:
            self.current[1].parts[-1] = q
        else:
            raise Exception

        print(q)
        print([f.get_title() for f in self.question_list])

        n_type = self.get_question_type(q)
        self.type[level] = n_type
        self.left_most_x[level] = q.x
        self.current[level] = q

    def set_question(self, q: Question, level: int):
        print(f"trying to set question ..(level={level})")
        self.set_page_number_for_first_detection(level)
        old_cur = self.current[level]
        if old_cur:
            if len(old_cur.parts) < 2:
                self.reset(level + 1)
            if level == 0:
                old_cur.y1 = (
                    q.y if self.curr_page in old_cur.pages else self.height
                )
        if level < 2:
            self.reset_current(level + 1)
            self.reset_types(level + 1)

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

        print(q)
        print([f.get_title() for f in self.question_list])

        n_type = self.get_question_type(q)
        self.type[level] = n_type
        self.left_most_x[level] = q.x

    def set_page_number_for_first_detection(self, level):
        if self.is_first_detection:
            self.is_first_detection = False
            if level > 0:
                self.current[0].pages.append(self.curr_page)
            if level > 1:
                self.current[1].pages.append(self.curr_page)

    def get_question_type(self, q: Question):
        n_type = ALPHAPET
        if type(q.label) is int or q.label.isdigit():
            n_type = NUMERIC
        elif checkIfRomanNumeral(q.label):
            n_type = ROMAN
        elif len(q.label) == 1:
            n_type = ALPHAPET
        else:
            raise Exception
        return n_type

    def get_allowed_startup_chars(self, level: int):
        used = None
        if level > 0:
            used = FIRST_MAP[self.type[level - 1]]
        res = [i for i in self.allowed_chars_startup if i != used]
        return res

    def get_alternative_allowed(self, level):
        # TODO: fix this
        n_type = self.type[level]
        curr: Question = self.current[level]
        """we can assume that this function will only be called if curr is already set
        following condition can be commented (if everything else is logically correct)
        I will leave it for debugging purposes uncommented"""
        if n_type == UNKNOWN and curr is not None:
            raise Exception("non sense : debug")

        if n_type == UNKNOWN or curr.label in self.allowed_chars_startup:
            return self.get_allowed_startup_chars(level)
        return str(curr.label)

    def get_next_allowed(self, level):
        n_type = self.type[level]
        curr = self.current[level]
        if n_type == UNKNOWN and curr is not None:
            raise Exception("non sense : debug")
        if n_type == UNKNOWN:
            return self.get_allowed_startup_chars(level)
        return get_next_label(curr.label, n_type)

    def is_char_valid_as_next(self, char, level, strict=False):
        next = self.get_next_allowed(level)
        if type(next) == list:
            return char in next
        next = str(next)
        if strict:
            return next == char
        return next.startswith(char)

    def is_char_valid_as_alternative(self, char, level, strict=False):
        # TODO: fix this
        """this is a dummy implementation, real implementation should allow rolling back
        into any breakpoint (prev question/part) in the past and continue from there,
        but here for simplicity we only allow rolling back one step , or completly discard
        everything ( logic in other code place )"""
        alternatives = self.get_alternative_allowed(level)
        if type(alternatives) == list:
            return char in alternatives
        alternatives = str(alternatives)
        if strict:
            return alternatives == char
        return alternatives.startswith(char)

    def is_char_x_weak_enough_to_ignore(self, diff, level):
        return diff > FACTORS[level] * self.tolerance

    def is_char_x_strong_enough_to_override(self, diff, level):
        return diff < FACTORS[level] * -self.tolerance

    def is_char_x_close_enough_to_append(self, diff, level):
        return abs(diff) <= FACTORS[level] * self.tolerance

    def is_char_skip(self, char, level):
        if level > 0:
            if char in self.current[level - 1].label:
                return True
        return not char or char in self.allowed_skip_chars

    def is_valid_neighbours(self, sym: Symbol, n_sym: Symbol):
        return sym.is_connected_with(n_sym)

    def print_internal_status(self, title):
        print(title)
        print("current left most = ", self.left_most_x)
        print("current types = ", self.type)
        print(
            "current types = ",
            [self.get_next_allowed(l) for l in range(3)],
        )

    def print_final_results(self, curr_file):
        print("\n\n")
        print("****************** Final Result ********************\n")
        if len(self.question_list) == 0:
            print(f"No question found on this exam ({curr_file}) ")
        else:
            print(
                f"found the following questions on pdf {curr_file} "  # [{self.current_page}]"
            )
            for q in self.question_list:
                print(q)

    def handle_sequence(self, seq: Sequence, page: int):
        if page != self.curr_page:

            self.print_internal_status("Befor:")
            print(
                f"\n***************** page {page} ({self.width},{self.height})**********************\n"
            )
            self.curr_page = page
            self.is_first_detection = True
            if len(self.question_list) == 0:
                self.reset(0)
                self.reset_left_most(0)
            self.print_internal_status("After:")
        for level in range(3):
            found = self.__handle_sequence(seq, level)
            if self.current[level] is None:
                break

    def __handle_sequence(self, seq: Sequence, level: int):
        # first_valid : Symbol | None = None
        prev_valid: Symbol | None = None
        is_next_candidate = False
        is_alternative_candidate = False

        char_all = ""
        char, x, y, h, diff, old_diff = "", 0, 0, 0, 0, 10000
        can_append, can_overwrite = None, None
        # is_alternative_better = False

        if self.current[level]:
            old_diff = self.current[level].x - self.left_most_x[level]
        for _, sym in enumerate(seq):
            sym: Symbol = sym
            char = sym.ch
            if self.is_char_skip(char, level):
                continue
            if prev_valid and not self.is_valid_neighbours(sym, prev_valid):
                break
            prev_valid = sym

            if diff == 0:
                x, y, x1, y1 = sym.get_box()
                h = y1 - y
                self.tolerance = x1 - x
                diff = x - self.left_most_x[level]

                if self.is_char_x_weak_enough_to_ignore(diff, level):
                    return False
                # is_alternative_better = abs(diff) < abs(old_diff)
                # if can_append is None:
                can_append = self.is_char_x_close_enough_to_append(diff, level)
                can_overwrite = self.is_char_x_strong_enough_to_override(
                    diff, level
                )

            valid_as_next = self.is_char_valid_as_next(char_all + char, level)
            valid_as_alt = self.is_char_valid_as_alternative(
                char_all + char, level
            )

            if valid_as_next:
                char_all += char
                is_next_candidate = True
                continue

            elif valid_as_alt:
                char_all += char
                is_alternative_candidate = True
                continue

            elif can_overwrite:

                print(f"\nL{level}: Ignored 'OVERRIDE' Seq: " + seq.get_text())
                pass
                # TODO: only adjust left_most_x , but don't set any thing new
                # if diff < -self.tolerance:  # and diff_upper > 0:
                #     self.reset(level)
                #     self.left_most_x[level] = x
            elif can_append:
                print(f"\nL{level}: Ignored 'APPEND' Seq: " + seq.get_text())
            elif valid_as_next or valid_as_alt:
                pass

            is_next_candidate = is_alternative_candidate = False
            return False

        if is_next_candidate and self.is_char_valid_as_next(
            char_all, level, strict=True
        ):

            print("\n" + seq.get_text())
            new_q = Question(char_all, self.curr_page, level, x, y, 2 * h)
            self.set_question(new_q, level)
            return True

        elif is_alternative_candidate and self.is_char_valid_as_alternative(
            char_all, level, strict=True
        ):

            print("\n" + seq.get_text())
            new_q = Question(char_all, self.curr_page, level, x, y, 2 * h)
            self.replace_question(new_q, level)
            return True

        else:
            return False

    def calc_page_segments_and_height(
        self, surface: cairo.ImageSurface, page_number: int, args
    ):

        out_height = 0
        self.page_segments[page_number] = []
        if args.type == "questions":
            if len(self.question_list) == 0:
                print("skipping empty page :", page_number)
                return
            d0 = self.question_list[0].h
        else:
            d0 = self.height * 0.01

        if args.type == "questions":
            segments = get_segments(surface, 0, self.height, d0, factor=0.5)
        else:
            segments = [(0, self.height, d0)]

        out_height += sum(seg_h + 2 * d2 for _, seg_h, d2 in segments)
        out_height += 2 * d0

        # ********************************************
        # parts = []
        # first_question = None
        # for i, q in enumerate(self.question_list):
        #     q: Question = q
        #     if page_number not in q.pages:
        #         continue
        #     if not first_question:
        #         first_question = q
        #     q_parts_in_page = find_questions_part_in_page(q, page_number)
        #     parts.extend(q_parts_in_page)
        # self.page_parts[page_number] = parts

        # *********************************************

        self.page_segments[page_number] = segments
        self.page_heights[page_number] = out_height

    def draw_all_pages_to_single_png(
        self,
        surf_dict: dict[int, cairo.ImageSurface],
        args,
        t_range: list[int],
        per_question: bool,
    ):
        pdf_file = args.curr_file
        if per_question:
            self.question_list[-1].y1 = self.height

        total_height = sum(self.page_heights.values())

        if total_height == 0:
            raise Exception("Total Height = 0")
            return None
        i = 0
        while True:

            height = total_height - (i / 10) * total_height
            try:
                out_surf = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32, self.width, int(height)
                )
                break
            except Exception as e:
                print(f"reducing suface height form {height} to ")
                i += 1
        out_ctx = cairo.Context(out_surf)

        out_ctx.set_source_rgb(1, 1, 1)  # White
        out_ctx.paint()
        out_ctx.set_source_rgb(0, 0, 0)  # Black
        self.dest_y = 0
        self.default_d0 = None
        if per_question:
            for nr in t_range:
                if nr > len(self.question_list):
                    continue
                q = self.question_list[nr - 1]
                for page in q.pages:
                    segments = self.page_segments.get(page) or []
                    q_segments = self.filter_question_segments(
                        q, segments, page
                    )
                    if not segments:
                        print(f"WARN: skipping page {page}, no Segments found")
                        continue
                    self.__draw_page_content(
                        q_segments, surf_dict[page], out_ctx
                    )

            pass
        else:
            for page, surf in surf_dict.items():
                if page in t_range:
                    segments = self.page_segments.get(page)
                    if not segments:
                        print(f"WARN: skipping page {page}, no Segments found")
                        continue
                    self.__draw_page_content(segments, surf, out_ctx)
        if self.dest_y == 0:
            return None
        exam_name = os.path.basename(pdf_file).split(".")[0]
        filename = f"output{sep}{exam_name}.png"
        out_surf = out_surf.create_for_rectangle(
            0, 0, self.width, self.dest_y + 2 * (self.default_d0)
        )
        out_surf.write_to_png(filename)
        return filename

    def filter_question_segments(
        self, q: Question, segments: list[tuple], curr_page
    ):
        q_segs = []
        q_pages = q.pages
        y0, y1 = 0, self.height
        if q_pages[0] == curr_page:
            y0 = q.y - 1.5 * q.h
        if q_pages[-1] == curr_page:
            y1 = q.y1 - 1.5 * q.h
        # print(y0, "   ", y1, "for debugging")
        # print("seq length = ", len(segments))
        for sy, sh, d0 in segments:
            if not self.default_d0 and d0:
                self.default_d0 = d0
            if sy < y1 and sy >= y0:
                q_segs.append((sy, sh, d0))
        return q_segs

    def __draw_page_content(
        self,
        segments: list,
        page_surf: cairo.ImageSurface,
        out_ctx: cairo.Context,
    ):
        d0 = None
        for i, (src_y, seg_h, d0) in enumerate(segments):
            if not self.default_d0 and d0:
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
            self.dest_y += h0 + (0.55 * d0)
        return d0

    # def export_whole_surface_to_png(self,pdf_file)


if __name__ == "__main__":
    syms = Sequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
