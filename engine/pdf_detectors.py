from os.path import sep
import cairo
import re
from models.core_models import Symbol, SymSequence
from models.question import QuestionBase
from models.question import Question
from .pdf_utils import get_next_label, checkIfRomanNumeral


cosole_print = print
file = None


def enable_detector_dubugging(pdf_path: str):
    global file
    file = open(f"output{sep}detector_output.md", "w", encoding="utf-8")
    print("## Pdf:", pdf_path, "\n")


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

    def handle_sequence(self, seq: SymSequence, page: int):
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
    def __init__(
        self,
    ) -> None:
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
                self.left_most_x[0] = self.LEVEL_2_X
            self.reset_left_most(1)

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


class QuestionDetectorV2(BaseDetector):
    def __init__(self) -> None:
        super().__init__()
        self.curr_page = -1
        self.height = 0  # will be set by attach
        self.width = 0  # will be set by attach
        self.MINIMAL_X_RATIO = 0.05  # ratio to calculate MINIMAL_X in attach
        self.MINIMAL_X = 0
        self.MAX_X_RATIO = 0.5  # ratio to calculate MAX_X in attach
        self.MAX_X = 0
        self.question_list: list[QuestionBase] = []
        self.current_levels: list[QuestionBase | None] = [
            None,
            None,
            None,
        ]  # to store current question/part/subpart being tracked
        self.level_x_zones: list[list[float]] = [
            [],
            [],
            [],
        ]  # to store observed x-coords of confirmed markers for each level
        self.level_expected_types: list[int] = [
            UNKNOWN,
            UNKNOWN,
            UNKNOWN,
        ]
        self.level_expected_labels: list[str | list[str] | None] = [
            None,
            None,
            None,
        ]
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
        ]  # same as original
        self.initial_marker_candidates = [
            "1",
            "a",
            "i",
        ]  # similar to allowed_chars_startup
        self.x_tolerance_pixels = 10  # a base tolerance for x-position matching
        self.MAX_X_ZONE_HISTORY = 5 # Max history for x-zone averaging

    def attach(self, page_width, page_height):
        super().attach(page_width, page_height)
        self.height = page_height
        self.width = page_width
        self.MINIMAL_X = self.MINIMAL_X_RATIO * page_width
        self.MAX_X = self.MAX_X_RATIO * page_width
        # Add any other initializations needed when a new page context is attached,
        # e.g., resetting level-specific states if not handled per page in handle_sequence
        # For now, we'll reset expected types and labels on new page if they shouldn't persist.
        # self.level_expected_types = [UNKNOWN, UNKNOWN, UNKNOWN]
        # self.level_expected_labels = [None, None, None]
        # self.level_x_zones = [[], [], []] # Reset x_zones per page too if desired

    def handle_sequence(self, seq: SymSequence, page: int):
        # Page Transition Logic
        if page != self.curr_page:
            if self.curr_page != -1: # If it's not the very first page
                # Finalize items ending on the previous page (self.curr_page)
                # The self.height here refers to the height of the *previous* page
                for level_idx in range(LEVEL_QUESTION, LEVEL_SUBPART + 1):
                    active_item = self.current_levels[level_idx]
                    if active_item:
                        # If y1 is still page bottom, it means it ends with the page
                        if active_item.y1 == self.height: # self.height is from previous page
                             # Ensure its end_page is the previous page
                            if self.curr_page not in active_item.pages: # Should be previous page number
                                active_item.pages.append(self.curr_page) # Mark it as ending on self.curr_page (previous)
                        # If an item's last known page (end_page) is the previous one,
                        # and its y1 is still set to that page's height, it's correctly terminated.
                        # If a new item on the *new* page already adjusted this via _update_question_structure,
                        # then y1 would be different.

            # Update to new page context (self.width, self.height are updated by attach)
            previous_page_height_for_spanning_y1_calc = self.height # store old height if needed for complex spanning
            self.curr_page = page
            self.level_x_zones = [[], [], []] # Reset x-zones for new page

            # For items that are continuing onto this new page:
            # Their y should be 0 (top of new page) effectively for content,
            # but their original y on their start_page remains.
            # Their y1 should also be reset to new page's height by default.
            for level_idx in range(LEVEL_QUESTION, LEVEL_SUBPART + 1):
                active_item = self.current_levels[level_idx]
                if active_item and active_item.end_page != page : # If it was not ended on previous page by a new sibling
                    if page not in active_item.pages: # If it's truly spanning to this new page
                        active_item.pages.append(page)
                    active_item.y1 = self.height # Extend to bottom of current new page by default
        
        # Main detection logic for the current sequence on the current page
        for level in range(LEVEL_QUESTION, LEVEL_SUBPART + 1):
            # Try to find a marker for the current level in any part of the sequence
            processed_for_level = False
            for sub_seq in seq.iterate_split(" \t"): # Original QuestionDetector uses " \t"
                if self._process_sub_sequence(sub_seq, level, page):
                    processed_for_level = True
                    # If a question (level 0) is found, we might want to immediately
                    # look for parts (level 1) and sub-parts (level 2) in the *same* sequence.
                    # So, we don't break here necessarily, allowing subsequent levels to be processed.
                    # However, once a level is processed, we probably don't need to check other sub_seq for the SAME level.
                    break 
            
            if not processed_for_level and self.current_levels[level] is None :
                 # If after checking all sub-sequences, no marker was found for this level,
                 # and there's no current item for this level, then we can't proceed to deeper levels.
                 break


    def _process_sub_sequence(self, sub_seq: SymSequence, level: int, page: int) -> bool:
        accumulated_chars = ""
        first_char_props = None # To store x, y, h of the first valid char of a potential marker

        if not sub_seq.symbols: # Skip empty sub_sequences
            return False

        for sym_idx, sym in enumerate(sub_seq.symbols):
            # Basic X validation
            if sym.x < self.MINIMAL_X or sym.x > self.MAX_X:
                # If we already started accumulating chars, and we hit a symbol outside X range,
                # it might be the end of our potential marker.
                if accumulated_chars:
                    break # Process what we have, then this sub_seq is done for this marker.
                else:
                    continue # Haven't started a marker yet, skip this sym.

            if self._is_skip_char(sym.ch, level):
                if not accumulated_chars: # Skip leading skip_chars
                    continue
                # If skip char is encountered after some accumulation, it might be part of marker e.g. "1. "
                # or it might be a separator. For now, let's assume skip chars in middle of text reset accumulation.
                # This means "1. (a)" would be "1." then "(a)".
                # A more robust way would be to check accumulated_chars + sym.ch first.
                # For now, if we have chars, and see a skip char, we process what we have.
                # Exception: if it's the *last* char and a common trailing one like "."
                if sym.ch != "." or sym_idx < len(sub_seq.symbols) -1 : # if "." is not last, or other skip char
                    potential_text_with_skip_char = accumulated_chars + sym.ch # check if it forms a valid marker with the skip char
                    is_marker, marker_label, marker_type = self._check_potential_marker(potential_text_with_skip_char, level, first_char_props['x'] if first_char_props else sym.x)
                    if is_marker:
                        accumulated_chars = potential_text_with_skip_char # Commit if it's a marker
                    # else, this skip char breaks the current accumulation
                    break # process current `accumulated_chars` (if any) then stop with this sub_seq.
            
            current_char = sym.ch
            if not first_char_props:
                first_char_props = {'x': sym.x, 'y': sym.y, 'h': sym.h}

            # Check if adding current_char still makes a potential marker
            # This is a lookahead: Is "accumulated_chars + current_char" a valid start?
            # For simplicity, we'll do the check after appending.
            
            accumulated_chars += current_char
            
            # Prematurely check if the current accumulated_chars form a valid marker
            # This helps in cases like "1. Introduction" where "1." is the marker.
            is_marker, marker_label, marker_type = self._check_potential_marker(accumulated_chars, level, first_char_props['x'])
            
            if is_marker:
                # If it is a marker, we need to see if the *next* char invalidates it (e.g. "1a" where "1" is numeric, "a" is alpha)
                # or if it's a multi-char marker like "iv."
                # For now, if it's a marker, we tentatively accept it.
                # More complex logic could check if a longer version is also a marker.
                
                # Example: "1. " vs "1.". If "1." is a marker, and next is " ", _is_skip_char handles it.
                # If "1" is marker, and next is ".", _check_potential_marker("1.") should catch it.
                # If "i" is marker, and next is "v", then "iv" should be checked.
                
                # Let's assume _check_potential_marker is good enough for now.
                # If a valid marker is found:
                q_base = QuestionBase(
                    label=marker_label,
                    pages=[page], # pages is a list, start_page is 'page'
                    level=level,
                    x=first_char_props['x'],
                    y=first_char_props['y'],
                    w=self.width, # Box width, using page width for now
                    page_height=self.height, # Page height for Box context
                    line_h=first_char_props['h'] # Symbol height
                )
                q_base.q_type = marker_type
                self._update_question_structure(q_base, level, page, first_char_props['x'])
                return True # Marker found and processed in this sub_sequence
        
        # After loop, check if remaining accumulated_chars (if any) form a marker
        # This handles cases where marker is at the end of sub_seq without trailing skip chars.
        if accumulated_chars and first_char_props:
            is_marker, marker_label, marker_type = self._check_potential_marker(accumulated_chars, level, first_char_props['x'])
            if is_marker:
                q_base = QuestionBase(
                    label=marker_label,
                    pages=[page], # pages is a list, start_page is 'page'
                    level=level,
                    x=first_char_props['x'],
                    y=first_char_props['y'],
                    w=self.width, # Box width, using page width for now
                    page_height=self.height, # Page height for Box context
                    line_h=first_char_props['h'] # Symbol height
                )
                q_base.q_type = marker_type
                self._update_question_structure(q_base, level, page, first_char_props['x'])
                return True
                
        return False # No marker found in this sub_sequence

    def _is_skip_char(self, sym_char: str, level: int) -> bool:
        # For now, level doesn't change skip characters.
        return sym_char in self.allowed_skip_chars

    def _get_marker_type_and_cleaned_label(self, text: str) -> tuple[int, str | None]:
        text = text.strip()
        # Attempt to match common question marker patterns
        # Numeric patterns: "1.", "1)", "1"
        m = re.match(r"^(\d+)[.)]?$", text)
        if m:
            return NUMERIC, m.group(1)

        # Alphabetic patterns: "(a)", "a.", "a)", "a"
        m = re.match(r"^\(?([a-zA-Z])\)?\.?$", text)
        if m:
            # Further check if it's a Roman numeral if it's 'i', 'v', 'x' etc.
            # This simple regex for roman is just illustrative, checkIfRomanNumeral is better
            if checkIfRomanNumeral(m.group(1).upper()): #checkIfRomanNumeral expects uppercase
                 # Check if the whole text is roman (e.g. "iv.", not just "i")
                cleaned_roman_text = re.sub(r"[().]", "", text).upper()
                if checkIfRomanNumeral(cleaned_roman_text):
                    return ROMAN, cleaned_roman_text.lower() # Store roman in lowercase consistent with other types
            return ALPHAPET, m.group(1).lower()


        # Roman numeral patterns: "i.", "i)", "(i)", "i" (also "IV.", "iv)")
        # Use a more robust way to strip punctuation for Roman check
        cleaned_text_for_roman = re.sub(r"[().]", "", text)
        if checkIfRomanNumeral(cleaned_text_for_roman.upper()): # try uppercase for safety
            return ROMAN, cleaned_text_for_roman.lower() # Store roman in lowercase

        return UNKNOWN, None

    def _check_potential_marker(self, text: str, level: int, x_pos: float) -> tuple[bool, str | None, int | None]:
        marker_type, marker_label = self._get_marker_type_and_cleaned_label(text)

        if marker_type == UNKNOWN or marker_label is None:
            return False, None, None

        # X-Position Validation
        if not self._is_x_pos_valid(x_pos, level):
            # print(f"DEBUG: X-pos invalid for '{text}' at level {level}, x={x_pos}. Expected near {self.level_x_zones[level]}")
            return False, None, None
        
        # Contextual Validation
        expected_type_for_level = self.level_expected_types[level]
        expected_label_for_level = self.level_expected_labels[level]

        if expected_type_for_level == UNKNOWN:
            # This is the first marker we are trying to establish for this level (or after a reset)
            if level == LEVEL_QUESTION:
                # For top-level questions, often starts with "1" or "1."
                # We can be more lenient or have specific rules e.g. must be NUMERIC if first ever q.
                if not self.question_list and marker_type != NUMERIC and marker_label != "1": # First question in doc must be "1"
                    # print(f"DEBUG: First question in doc must be '1' (NUMERIC). Got {marker_label} ({marker_type})")
                    # return False, None, None # Too restrictive for now, allow any initial type
                    pass 
                return True, marker_label, marker_type
            
            elif level > LEVEL_QUESTION:
                # For parts/subparts, a parent must exist
                if self.current_levels[level - 1] is None:
                    # print(f"DEBUG: Parent for level {level} not found for marker '{text}'")
                    return False, None, None # Cannot have a part without a question, or subpart without part.
                
                # Parent exists. Is this new marker type compatible as a follow-up?
                # E.g. Q1 -> (a) is fine. Q1 -> (i) is fine.
                # Q(a) -> i. is fine.
                # For now, accept any valid marker type if parent exists and current level type is UNKNOWN
                return True, marker_label, marker_type

        else: # Expected type for this level is KNOWN
            if marker_type != expected_type_for_level:
                # print(f"DEBUG: Type mismatch for '{text}'. Expected {expected_type_for_level}, got {marker_type}")
                return False, None, None # Type mismatch with expectation
            
            if isinstance(expected_label_for_level, list): # E.g. after "1", next could be "a" or "i"
                if marker_label not in expected_label_for_level:
                    # print(f"DEBUG: Label mismatch for '{text}'. Expected one of {expected_label_for_level}, got {marker_label}")
                    return False, None, None
            elif expected_label_for_level is not None and marker_label != expected_label_for_level:
                # print(f"DEBUG: Label mismatch for '{text}'. Expected {expected_label_for_level}, got {marker_label}")
                return False, None, None # Label mismatch with expectation
            
            # If all checks pass (type matches, label matches)
            return True, marker_label, marker_type
            
        return True, marker_label, marker_type # Fallback, should be covered by logic above

    def _is_x_pos_valid(self, x_pos: float, level: int) -> bool:
        if not self.level_x_zones[level]: # No markers confirmed for this level yet on this page/context
            # For a new level, x_pos is valid if it's within the global MINIMAL_X and MAX_X
            # This was already checked before calling _process_sub_sequence sym loop.
            return True 
        
        # Markers have been confirmed, compare to average
        average_x = sum(self.level_x_zones[level]) / len(self.level_x_zones[level])
        # Tolerance can increase slightly for sub-levels, or be a config parameter
        allowed_delta = self.x_tolerance_pixels * (1 + level * 0.5) # e.g. L0: 10px, L1: 15px, L2: 20px
        
        is_valid = abs(x_pos - average_x) < allowed_delta
        # if not is_valid:
            # print(f"DEBUG: x_pos {x_pos} for level {level} is outside tolerance. Avg: {average_x}, Delta: {allowed_delta}")
        return is_valid

    def _update_question_structure(self, new_q_base: QuestionBase, level: int, page: int, x_pos: float):
        previous_sibling: QuestionBase | None = None

        # Set y1 for Previous Sibling on the same page
        if level == LEVEL_QUESTION:
            if self.question_list:
                # Check if there's a current question at LEVEL_QUESTION that is ending.
                # This can be complex if a new Q1 starts while a Q0 was active without parts.
                # For now, simple previous sibling from the main list.
                last_q_on_main_list = self.question_list[-1]
                if last_q_on_main_list.end_page == new_q_base.start_page:
                    previous_sibling = last_q_on_main_list
        elif level == LEVEL_PART:
            parent_question = self.current_levels[LEVEL_QUESTION]
            if parent_question and parent_question.parts:
                last_part = parent_question.parts[-1]
                if last_part.end_page == new_q_base.start_page:
                    previous_sibling = last_part
        elif level == LEVEL_SUBPART:
            parent_part = self.current_levels[LEVEL_PART]
            if parent_part and parent_part.parts:
                last_subpart = parent_part.parts[-1]
                if last_subpart.end_page == new_q_base.start_page:
                    previous_sibling = last_subpart
        
        if previous_sibling and previous_sibling.y1 == self.height : # Only update if it was extending to page bottom
            previous_sibling.y1 = new_q_base.y
            # Update end_page of previous sibling if it was single page and new one starts on same page.
            # Multi-page spanning y1 setting is more for page transitions / on_finish.
            # For now, this is okay.

        # Link Parent and Child & Update question_list
        if level == LEVEL_QUESTION:
            self.question_list.append(new_q_base)
        elif level == LEVEL_PART:
            parent_question = self.current_levels[LEVEL_QUESTION]
            if parent_question:
                parent_question.parts.append(new_q_base)
            else:
                # This case (a part without a current question) should ideally be prevented by _check_potential_marker
                print(f"WARN: LEVEL_PART '{new_q_base.label}' found without parent question. Page: {page}, X: {x_pos}")
                # Potentially create a dummy parent or skip? For now, it won't be linked.
                return # Or handle error more gracefully
        elif level == LEVEL_SUBPART:
            parent_part = self.current_levels[LEVEL_PART]
            if parent_part:
                parent_part.parts.append(new_q_base)
            else:
                print(f"WARN: LEVEL_SUBPART '{new_q_base.label}' found without parent part. Page: {page}, X: {x_pos}")
                return # Or handle error

        # Update current_levels
        # Before updating current_levels[level], if there was an existing item at this level,
        # and it's on the same page and its y1 is still self.height, it means it's ending here.
        # This is slightly different from previous_sibling logic which was for true previous on the list.
        # This handles implicit endings: e.g. Q1 followed by Q2 on same page.
        
        # Consider current item at this level before overwriting
        current_item_at_this_level = self.current_levels[level]
        if current_item_at_this_level and current_item_at_this_level != new_q_base: # Ensure not same object
             if current_item_at_this_level.end_page == new_q_base.start_page and \
                current_item_at_this_level.y1 == self.height:
                 current_item_at_this_level.y1 = new_q_base.y

        self.current_levels[level] = new_q_base

        # Update Expectations for this level
        if new_q_base.q_type is not None and new_q_base.label is not None:
            self.level_expected_types[level] = new_q_base.q_type
            self.level_expected_labels[level] = get_next_label(new_q_base.label, new_q_base.q_type)
        else: # Should not happen if q_type and label are properly set from _check_potential_marker
            self.level_expected_types[level] = UNKNOWN
            self.level_expected_labels[level] = None
            print(f"WARN: new_q_base '{new_q_base.label}' has no q_type for level {level}. Expectations not set.")


        # Manage X-Zone
        self.level_x_zones[level].append(x_pos)
        if len(self.level_x_zones[level]) > self.MAX_X_ZONE_HISTORY:
            self.level_x_zones[level].pop(0)

        # Reset Deeper Levels' state
        if level == LEVEL_QUESTION:
            levels_to_reset = [LEVEL_PART, LEVEL_SUBPART]
        elif level == LEVEL_PART:
            levels_to_reset = [LEVEL_SUBPART]
        else:
            levels_to_reset = []

        for deeper_level in levels_to_reset:
            # If there was an active item at a deeper level, and it's on the same page, its y1 should be set.
            # This is tricky because its y1 should be new_q_base.y if new_q_base is truly "above" it.
            # For now, this reset is primarily for clearing expectations and current pointers.
            # Y1 of implicitly ended deeper items needs careful handling, possibly in page transitions or on_finish.
            # For now, if a new Q/P starts, previous sub-items on same page are assumed to end at new_q_base.y
            if self.current_levels[deeper_level] and \
               self.current_levels[deeper_level].end_page == new_q_base.start_page and \
               self.current_levels[deeper_level].y1 == self.height:
                 self.current_levels[deeper_level].y1 = new_q_base.y

            self.current_levels[deeper_level] = None
            self.level_expected_types[deeper_level] = UNKNOWN
            self.level_expected_labels[deeper_level] = None
            self.level_x_zones[deeper_level] = [] # Clear x-zones for deeper levels as context changes


        # print(f"DEBUG (UpdateStruct): Level {level} marker: {new_q_base.label} (Type: {new_q_base.q_type}) at x={x_pos:.2f}, y={new_q_base.y:.2f}, y1={new_q_base.y1:.2f} on page {page}. Next for L{level}: {self.level_expected_labels[level]}")
        # if level == LEVEL_QUESTION and self.question_list:
        #     print(f"DEBUG (UpdateStruct): QList: {[q.label + '(' + str(q.y) + '-' + str(q.y1) + ')' for q in self.question_list]}")
        # if self.current_levels[LEVEL_QUESTION]:
        #     print(f"DEBUG (UpdateStruct): Q {self.current_levels[LEVEL_QUESTION].label} parts: {[p.label + '(' + str(p.y) + '-' + str(p.y1) + ')' for p in self.current_levels[LEVEL_QUESTION].parts]}")
        # if self.current_levels[LEVEL_PART]:
        #      print(f"DEBUG (UpdateStruct): P {self.current_levels[LEVEL_PART].label} subparts: {[sp.label + '(' + str(sp.y) + '-' + str(sp.y1) + ')' for sp in self.current_levels[LEVEL_PART].parts]}")


    def get_question_list(self, pdf_file_name_or_path) -> list[Question]:
        # Final pass to ensure all y1 are set correctly, especially for last items on a page / document.
        # This might be better in on_finish()
        for q_base in self.question_list:
            if q_base.y1 is None: # Should have been page_height by default
                q_base.y1 = self.height 
            for part in q_base.parts:
                if part.y1 is None: part.y1 = self.height
                for subpart in part.parts:
                    if subpart.y1 is None: subpart.y1 = self.height
        
        q_list = []
        for i, q in enumerate(self.question_list):
            q_list.append(Question.from_base(q, pdf_file_name_or_path, i + 1))
        return q_list

    def on_finish(self):
        # This method is called after all pages are processed.
        # Finalize any open items at all levels.
        # self.height here is the height of the very last page processed.
        for level_idx in range(LEVEL_QUESTION, LEVEL_SUBPART + 1):
            active_item = self.current_levels[level_idx]
            if active_item:
                # If y1 is still pointing to the page height, it means it ends with the document.
                # Or if its y1 was set to a previous page's height (meaning it ended there)
                # and no new item closed it.
                # The default y1 in QuestionBase is page_height, so if it wasn't updated by a subsequent
                # item on the same page, it means it extends to page end.
                if active_item.y1 == self.height: # Check if it extends to current (last) page's bottom
                    pass # y1 is already correctly set to page_height by default or page transition
                
                # Ensure end_page is correctly set to the last processed page (self.curr_page)
                # if it was active and not explicitly ended earlier on a previous page.
                if active_item.end_page != self.curr_page:
                    # This implies it was thought to end on an earlier page, but was still 'current'.
                    # Or it started on an earlier page and spans to the end.
                    if self.curr_page not in active_item.pages:
                         active_item.pages.append(self.curr_page) # Ensure its page range includes the last page
                
                # If an item's y1 is still None (should not happen due to default in QuestionBase)
                # or if it's less than its start y (error), set to page height.
                if active_item.y1 is None or (active_item.y1 is not None and active_item.y1 < active_item.y and active_item.start_page == active_item.end_page):
                    active_item.y1 = self.height

        # No aggressive pruning as per instructions.
        # The get_question_list method also has a fallback for y1, which might be redundant now
        # but harmless.


if __name__ == "__main__":
    syms = SymSequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
