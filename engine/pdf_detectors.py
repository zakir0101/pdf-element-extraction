# import enum
# from math import isnan
# import time
# import re
# import string
# import sys
# from typing import Tuple
# from .create_cairo_font import open_image_in_irfan
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
from .pdf_utils import get_next_label, checkIfRomanNumeral


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

LEVEL_QUESTION = 0
LEVEL_PART = 1
LEVEL_SUBPART = 2

TITLE_DICT = ["Question", "PART", "SUBPART"]


class Question(Box):

    TITLE_DICT = ["Question", "PART", "SUBPART"]

    def __init__(
        self, label: int | str, page: int, level: int, x: int, y: int, h: int
    ):
        super().__init__()
        self.parts: Question = []
        self.label: int | str = label
        self.pages: int = [page]
        self.level: int = level
        self.contents: list[Box] = []
        self.x: int = x
        self.y: int = y
        self.h: int = h

    def __str__(self):
        in_page = f" In Page {self.pages[0]}" if self.level == 0 else ""
        rep = (
            " " * self.level * 4
            + TITLE_DICT[self.level]
            + " "
            + self.label
            + in_page
            + f"(x={self.x}, y={self.y})"
            + "\n"
        )
        for p in self.parts:
            rep += str(p)
        return rep


class QuestionDetector(BaseDetector):
    def __init__(self) -> None:
        super().__init__()
        self.curr_page = -1
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
        else:
            raise Exception

        self.current[level:] = [None] * (3 - level)

    def set_question(self, q: Question, level: int):
        old_cur = self.current[level]
        if old_cur and len(old_cur.parts) < 2:
            self.reset(level + 1)
        if level < 2:
            self.current[level + 1 :] = [None] * (3 - level + 1)
            # self.type[level+1:] = [UNKNOWN] * (3 - level)

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
            # print("************************************")
            # print(res)
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
                # upper_x = (
                #     self.left_most_x[level - 1]
                #     if (level > 0 and self.current[level - 1])
                #     else 0
                # )
                # diff_upper = upper_x - x

                if self.is_char_skip(char, level):
                    continue
                if not self.is_char_valid(char, level):
                    # print("char ", char, ", is not valid for level", level)
                    is_candidate = False
                    # if diff < -self.tolerance:  # and diff_upper > 0:
                    #     self.reset(level)
                    #     self.left_most_x[level] = x
                    break

                # if diff_upper > 0:
                #     print("too much left for this level=", level)
                #     print("x=", x, ", upper_x=", upper_x)
                #     is_candidate = False
                #     break

                if diff > self.tolerance:
                    print(f"too low value for level {level} , ignoring it")
                    print("x=", x, ", diff=", diff)
                    is_candidate = False
                    break

                # first_valid = sym
                prev_valid = sym
                is_candidate = True
                char_all = char
                if level == 1:
                    print("aim here ,char is ", char)
            else:
                if level == 1:
                    print("aim here 2 ,char is ", char)
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
            print("found candidates for level :", level, "and char", char_all)
            print("diff is ", diff, ", tolerence is ", self.tolerance)
            new_q = Question(char_all, self.curr_page, level, x, y, 2 * h)
            if diff < -self.tolerance:
                print("resetting to char ", char_all)
                self.reset(level)
            self.set_question(new_q, level)
            return True
        else:
            return False


if __name__ == "__main__":
    syms = Sequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
