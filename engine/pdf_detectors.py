from os.path import sep
import cairo
from models.core_models import Symbol, SymSequence
from models.question import QuestionBase
from models.question import Question
from .pdf_utils import get_next_label, checkIfRomanNumeral


cosole_print = print
file = None


def enable_detector_dubugging():
    global file
    file = open(f"output{sep}detector_output.md", "w", encoding="utf-8")


def print(*args):
    global file
    if not file:
        return
    args = [str(a) for a in args]
    file.write(" ".join(args) + "\n")
    file.flush()


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


class BaseDetector:
    def __init__(self) -> None:
        pass

    def attach(self, page_width, page_height):
        self.height = page_height
        self.width = page_width

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


# def find_questions_part_in_page(
#
#     q: QuestionBase, page: int
# ) -> list[QuestionBase]:
#     parts: list[QuestionBase] = []
#     if page not in q.pages:
#         return []
#
#     if len(q.pages) == 1:
#         parts.append(q)
#     else:
#         for p in q.parts:
#             parts.extend(find_questions_part_in_page(p, page))
#     return parts


class QuestionDetector(BaseDetector):
    def __init__(self) -> None:
        super().__init__()
        self.curr_page = -1
        self.height = 0
        self.width = 0
        self.MINIMAL_X = 0
        self.LEVEL_2_X = None
        self.is_first_detection = True
        self.out_surf: cairo.ImageSurface | None = None
        self.out_ctx: cairo.Context | None = None
        self.page_segments: dict[int, list[tuple]] = {}
        self.page_parts: dict[int, list[QuestionBase]] = {}
        self.page_parts_per_question: dict[int, dict[int, QuestionBase]] = {}
        self.page_heights: dict[int, int] = {}
        self.allowed_skip_chars = [
            " ",
            "\u0008",
            "\u2002",
            "(",
            "[",
            "",
            ")",
            "]",
            ".",
        ]
        self.allowed_chars_startup = ["1", "a", "i"]

        self.tolerance = 20
        self.question_list: list[QuestionBase] = []

        self.left_most_x: list[int] = [0] * 3
        self.current: list[QuestionBase] = [None, None, None]
        self.type: list[int] = [UNKNOWN, UNKNOWN, UNKNOWN]
        pass

    def attach(self, page_width, page_height):
        super().attach(page_width, page_height)
        self.MINIMAL_X = 0.05 * page_width
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

    def replace_question(self, q: QuestionBase, level: int):
        old_curr = self.current[level]
        if old_curr and len(old_curr.parts) > 1:

            # if (
            #     level == 0
            #     and self.type[0] != NUMERIC
            #     and q.label == "1"
            #     and self.curr_page <= 4
            # ):
            #     # NOTE:improve me, this should not happen from the begining, this workaround is ver specific to IGCSE
            #     print(
            #         "# NOTE: We will replace the old existing question, though it already detected +2 part"
            #     )
            # else:
            print(
                "Can not replace old question because it already has detected 2+ parts"
            )
            return
        elif (
            old_curr
            and len(old_curr.parts) > 0
            and len(old_curr.parts[0].parts) > 1
        ):

            # Commented same as abode ....
            # truncated ...
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

    def on_finish(
        self,
    ):
        """call this function after all pages has beeing prcessed"""
        last = self.current[0]
        if not last:
            return
        last.y1 = self.height
        if len(last.parts) < 2:
            last.parts = []
        if last.parts and len(last.parts[-1].parts) < 2:
            last.parts[-1].parts = []

    def set_question(self, q: QuestionBase, level: int):
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
            if len(self.current[0].parts) > 1:
                print("setting LEVEL_2_X")
                self.LEVEL_2_X = q.x + 2 * q.h
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

    def get_question_type(self, q: QuestionBase):
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
        if level == 0:  # WARN:
            """this work only for cambrdige IGCSE ..."""
            return "1"
        else:
            used = FIRST_MAP[self.type[level - 1]]
        res = [i for i in self.allowed_chars_startup if i != used]
        return res

    def get_alternative_allowed(self, level):
        # TODO: fix this
        n_type = self.type[level]
        curr: QuestionBase = self.current[level]
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
        if isinstance(next, list):
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
        if isinstance(alternatives, list):
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

    def is_char_skip(self, sym: Symbol, level):
        char = sym.ch
        if sym.x < self.MINIMAL_X:
            return True
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
            [self.get_next_allowed(lev) for lev in range(3)],
        )

    def print_final_results(self, curr_file):
        print = cosole_print
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

    def handle_sequence(self, seq: SymSequence, page: int):
        if page != self.curr_page:

            self.print_internal_status("Befor:")
            print(
                f"\n***************** page {page} ({self.width},{self.height})**********************\n"
            )
            self.curr_page = page
            self.width
            self.is_first_detection = True
            if len(self.question_list) == 0:
                self.reset(0)
            if self.LEVEL_2_X:
                self.reset_left_most(1)
                self.left_most_x[0] = self.LEVEL_2_X
            else:
                self.reset_left_most(0)

            self.print_internal_status("After:")

        for level in range(3):
            for sub_seq in seq.iterate_split(" \t"):
                found = self.__handle_sequence(sub_seq, level)
                if found:
                    break

            if self.current[level] is None:
                break

    def __handle_sequence(self, seq: SymSequence, level: int):
        # first_valid : Symbol | None = None
        prev_valid: Symbol | None = None
        is_next_candidate = False
        is_alternative_candidate = False
        is_overwrite_and_reset = False

        char_all = ""
        char, x, y, symbole_height, diff = "", 0, 0, 0, None
        # old_diff = 10000
        can_append, can_overwrite = None, None
        # is_alternative_better = False

        # if self.current[level]:
        #     old_diff = self.current[level].x - self.left_most_x[level]
        for _, sym in enumerate(seq):
            sym: Symbol = sym
            char = sym.ch
            if self.is_char_skip(sym, level):
                continue
            if prev_valid and not self.is_valid_neighbours(sym, prev_valid):
                break
            prev_valid = sym

            if diff is None:
                x, y, x1, y1 = sym.get_box()
                symbole_height = y1 - y
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

            # if (
            #     self.type[0] != NUMERIC
            #     and char == "1"
            #     and can_overwrite
            #     and level == 0
            #     and self.curr_page <= 4
            # ):
            #     is_overwrite_and_reset = True
            #     break
            if valid_as_next:
                char_all += char
                is_next_candidate = True
                continue

            elif valid_as_alt:
                char_all += char
                is_alternative_candidate = True
                continue

            elif can_overwrite:
                print(
                    f"\nL{level}: Ignored 'OVERRIDE' Seq:(charall={char_all},char={char}) "
                    + seq.get_text()
                )
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

        if is_overwrite_and_reset:
            print("OV_AND_RESET :\n" + seq.get_text())
            self.reset(0)  # current level == 0
            new_q = QuestionBase(
                "1",
                self.curr_page,
                level,
                x,
                y,
                self.width,
                self.height,
                2 * symbole_height,
            )
            self.set_question(new_q, level)
            return True

        elif is_next_candidate and self.is_char_valid_as_next(
            char_all, level, strict=True
        ):

            print("\n" + seq.get_text())
            new_q = QuestionBase(
                char_all,
                self.curr_page,
                level,
                x,
                y,
                self.width,
                self.height,
                2 * symbole_height,
            )
            self.set_question(new_q, level)
            return True

        elif is_alternative_candidate and self.is_char_valid_as_alternative(
            char_all, level, strict=True
        ):

            print("\n" + seq.get_text())
            new_q = QuestionBase(
                char_all,
                self.curr_page,
                level,
                x,
                y,
                self.width,
                self.height,
                2 * symbole_height,
            )
            self.replace_question(new_q, level)
            return True

        else:
            return False

    def get_question_list(self, pdf_file_name_or_path) -> list[Question]:
        q_list = []
        for i, q in enumerate(self.question_list):
            q_list.append(Question.from_base(q, pdf_file_name_or_path, i + 1))
        return q_list

    # def preset_detectors(self, height, width, q_list: list[QuestionBase]):
    #     self.width = width
    #     self.height = height
    #     self.question_list = q_list


if __name__ == "__main__":
    syms = SymSequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
