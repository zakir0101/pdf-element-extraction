from os.path import sep
import re # For regular expressions
try:
    import cairo
except ModuleNotFoundError:
    print("WARNING: Cairo module not found. Some functionalities may be limited.") # Or pass, if no fallback
    cairo = None # So references to cairo don't cause NameError

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


class QuestionDetectorV2(BaseDetector):
    def __init__(self):
        super().__init__()
        # self.detected_questions: list[Question] = [] # Replaced by questions_list for QuestionBase
        self.current_line_symbols: list[Symbol] = []
        self.last_symbol_on_line: Symbol | None = None
        self.processed_lines: list[SymSequence] = [] # For temporary storage/debugging
        self.current_page_number: int = -1
        self.VERTICAL_ALIGNMENT_TOLERANCE: float = 2.0
        self.HORIZONTAL_PROXIMITY_TOLERANCE: float = 10.0
        
        self.questions_list: list[QuestionBase] = []
        self.current_question_level_0: QuestionBase | None = None
        self.current_question_level_1: QuestionBase | None = None
        self.current_question_level_2: QuestionBase | None = None
        self.page_width: float = 0.0
        self.page_height: float = 0.0
        # print("QuestionDetectorV2 initialized for question detection")

    def _extract_numbering_pattern(self, line_text: str) -> tuple[str | None, str | None, str | None]:
        line_text = line_text.strip()
        
        # Regex patterns:
        # - Optional prefix (Question, Q, Part) - non-capturing for prefix, but we'll extract it if present
        # - Main number/letter (numeric, alpha, roman)
        # - Optional suffix char ('.', ')')

        # Pattern for "Question 1", "Q1", "1.", "1)", etc.
        # ((?:Question|Q)\s*)? - Optional prefix "Question " or "Q" (non-capturing group for prefix words, capturing for the whole prefix part)
        # (\d+) - Numeric part (capturing)
        # (\.|\))? - Optional suffix "." or ")" (capturing)
        pat_numeric = re.compile(r"^(?:(Question|Q)\s*)?(\d+)\s*([.)])?", re.IGNORECASE)

        # (\d+) - Numeric part (capturing)
        # (\.|\))? - Optional suffix "." or ")" (capturing)
        pat_numeric = re.compile(r"^(?:(Question|Q)\s*)?(\d+)\s*([.)])?", re.IGNORECASE)

        # Pattern for alpha:
        # Group 1: Prefix (Part)
        # Group 2: Letter if in parentheses, e.g., (a) - includes the parens
        # Group 3: Letter if not in parentheses, e.g., a
        # Group 4: Suffix char like . or ) that might follow the letter or the parenthesized expression
        pat_alpha = re.compile(r"^(?:(Part)\s*)?(?:(\([a-zA-Z]\))|([a-zA-Z]))\s*([.)])?", re.IGNORECASE)

        # Pattern for roman:
        # Group 1: Prefix (Part)
        # Group 2: Roman numeral if in parentheses - includes the parens
        # Group 3: Roman numeral if not in parentheses
        # Group 4: Suffix char
        pat_roman = re.compile(r"^(?:(Part)\s*)?(?:(\([ivxlcdmIVXLCDM]+\))|([ivxlcdmIVXLCDM]+))\s*([.)])?", re.IGNORECASE)
        
        # Try Numeric
        match_numeric = pat_numeric.match(line_text)
        if match_numeric:
            prefix = match_numeric.group(1)
            number = match_numeric.group(2)
            suffix = match_numeric.group(3)
            if prefix: prefix = prefix.strip()
            return prefix, number, suffix

        # Try Roman
        match_roman = pat_roman.match(line_text)
        if match_roman:
            prefix = match_roman.group(1)
            number_in_parens = match_roman.group(2) # e.g., "(i)"
            number_no_parens = match_roman.group(3) # e.g., "i"
            external_suffix = match_roman.group(4)   # e.g., "." in "(i)." or "i."
            
            number_val = None
            internal_suffix = None

            if number_in_parens: # e.g. "(i)" or "(iv)"
                number_val = number_in_parens[1:-1] # Extract "i" from "(i)"
                internal_suffix = number_in_parens[-1] # Capture ')' as potential suffix
            else: # e.g. "i" or "iv"
                number_val = number_no_parens
            
            if number_val and checkIfRomanNumeral(number_val):
                if prefix: prefix = prefix.strip()
                # Prioritize external_suffix. If not present and item was parenthesized, use its closing paren.
                final_suffix = external_suffix if external_suffix else (internal_suffix if number_in_parens else None)
                return prefix, number_val, final_suffix
            elif match_roman.group(0): # Structural match (like "ixl.") but content invalid
                return None, None, None # Prevent fall-through

        # Try Alpha
        match_alpha = pat_alpha.match(line_text)
        if match_alpha:
            prefix = match_alpha.group(1)
            letter_in_parens = match_alpha.group(2) # e.g., "(a)"
            letter_no_parens = match_alpha.group(3) # e.g., "a"
            external_suffix = match_alpha.group(4)   # e.g., "." in "(a)." or "a."

            number_val = None
            internal_suffix = None

            if letter_in_parens: # e.g. "(a)"
                number_val = letter_in_parens[1:-1] # Extract "a"
                internal_suffix = letter_in_parens[-1] # Capture ')'
            else: # e.g. "a"
                number_val = letter_no_parens

            if number_val:
                if letter_no_parens: # Apply refined heuristic for non-parenthesized letters
                    if not external_suffix: # No '.', ')' directly after the letter in the regex match
                        # Check what comes after the letter in the line
                        idx_after_letter_content = match_alpha.end(3) # End position of the letter itself in the stripped line_text
                        
                        remaining_text = line_text[idx_after_letter_content:].lstrip() # Strip leading spaces from the remainder
                        
                        if remaining_text and remaining_text[0].isalpha():
                            # If the text immediately following the letter (after stripping leading spaces from remainder)
                            # starts with another letter, then it's likely part of a word or a new word starting too close.
                            return None, None, None
                
                # If the heuristic didn't reject it, proceed.
                if prefix: prefix = prefix.strip()
                final_suffix = external_suffix if external_suffix else (internal_suffix if letter_in_parens else None)
                return prefix, number_val, final_suffix
        
                prefix_str = None
                if prefix_match:
                    prefix_str = prefix_match.strip()
                
                return prefix_str, number_match, suffix_match
        
        return None, None, None

    def _process_buffered_line(self):
        if self.current_line_symbols:
            assembled_line_sequence = SymSequence(self.current_line_symbols)
            line_text = assembled_line_sequence.get_text(verbose=False).strip()
            
            # print(f"Processing assembled line (Page {self.current_page_number}): {line_text}") # Original print
            
            prefix, number_str, suffix = self._extract_numbering_pattern(line_text) # Renamed 'number' to 'number_str' for clarity

            number_type: str | None = None
            if number_str:
                if number_str.isdigit():
                    number_type = 'numeric'
                elif checkIfRomanNumeral(number_str):
                    if number_str.islower():
                        number_type = 'roman_lower'
                    else:
                        number_type = 'roman_upper' # Could be mixed, but primarily upper
                elif number_str.isalpha():
                    if number_str.islower():
                        number_type = 'alpha_lower'
                    else:
                        number_type = 'alpha_upper'
            
            # Print detected numbering info (can be combined with line processing print)
            if number_str is not None:
                print(f"Detected numbering: Type='{number_type}', Prefix='{prefix}', Number='{number_str}', Suffix='{suffix}' on line (Page {self.current_page_number}): '{line_text}'")
            else:
                print(f"Processing assembled line (Page {self.current_page_number}): {line_text} (No numbering detected)")

            
            q_line_x = assembled_line_sequence.x
            q_line_y = assembled_line_sequence.y
            q_line_h = assembled_line_sequence.h

            # Level 0 Question Detection (Numeric)
            if number_type == 'numeric':
                # Finalize previous L0, L1, L2 if they exist
                if self.current_question_level_0 is not None:
                    if self.current_question_level_2 is not None: # An L2 part was open
                        self.current_question_level_2.y1 = q_line_y
                        # L2 should already be in L1.parts
                        print(f"Finalized Level 2: {self.current_question_level_2.label} (under L1: {self.current_question_level_1.label if self.current_question_level_1 else 'None'}) at y={q_line_y} due to new L0 start.")
                        self.current_question_level_2 = None
                    if self.current_question_level_1 is not None: # An L1 part was open
                        self.current_question_level_1.y1 = q_line_y
                        # L1 should already be in L0.parts
                        print(f"Finalized Level 1: {self.current_question_level_1.label} (under L0: {self.current_question_level_0.label}) at y={q_line_y} due to new L0 start.")
                        self.current_question_level_1 = None
                    
                    self.current_question_level_0.y1 = q_line_y
                    self.questions_list.append(self.current_question_level_0)
                    print(f"Finalized Question: {self.current_question_level_0.label}, Ended at y={q_line_y} on page {self.current_question_level_0.pages[0] if self.current_question_level_0.pages else 'N/A'}")

                # Create new QuestionBase for Level 0
                label = number_str
                level = 0
                new_q_l0 = QuestionBase(label, self.current_page_number, level, q_line_x, q_line_y, self.page_width, self.page_height, q_line_h)
                self.current_question_level_0 = new_q_l0
                self.current_question_level_1 = None 
                self.current_question_level_2 = None
                print(f"Started Level 0 Question: {label} at y={q_line_y} on page {self.current_page_number}")

            # Level 1 Part Detection (Alphabetic)
            elif number_type in ['alpha_lower', 'alpha_upper']:
                if self.current_question_level_0 is None:
                    print(f"WARNING: Attempted to start Level 1 part without active Level 0 question. Line: '{line_text}'")
                else:
                    if self.current_question_level_2 is not None: # An L2 part was open under the previous L1
                        self.current_question_level_2.y1 = q_line_y
                        # L2 should already be in L1.parts if L1 exists
                        if self.current_question_level_1:
                             print(f"Finalized Orphaned Level 2: {self.current_question_level_2.label} (under L1: {self.current_question_level_1.label}) at y={q_line_y} due to new L1 start.")
                        else: # Should not happen if L2 was active
                             print(f"Finalized Orphaned Level 2: {self.current_question_level_2.label} (L1 is None) at y={q_line_y} due to new L1 start.")
                        self.current_question_level_2 = None
                    
                    if self.current_question_level_1 is not None: # An L1 part was already open
                        self.current_question_level_1.y1 = q_line_y
                        # L1 should already be in L0.parts
                        print(f"Finalized Level 1: {self.current_question_level_1.label} (under L0: {self.current_question_level_0.label}) at y={q_line_y} due to new L1 start.")

                    label = number_str
                    level = 1
                    new_q_l1 = QuestionBase(label, self.current_page_number, level, q_line_x, q_line_y, self.page_width, self.page_height, q_line_h)
                    self.current_question_level_1 = new_q_l1
                    self.current_question_level_0.parts.append(new_q_l1)
                    self.current_question_level_2 = None # Reset L2
                    print(f"Started Level 1 Part: {label} under Question {self.current_question_level_0.label} at y={q_line_y} on page {self.current_page_number}")

            # Level 2 Sub-Part Detection (Roman)
            elif number_type in ['roman_lower', 'roman_upper']:
                if self.current_question_level_1 is None:
                    print(f"WARNING: Attempted to start Level 2 sub-part without active Level 1 part. Line: '{line_text}'")
                else:
                    if self.current_question_level_2 is not None: # An L2 part was already open
                        self.current_question_level_2.y1 = q_line_y
                        # L2 should already be in L1.parts
                        print(f"Finalized Level 2: {self.current_question_level_2.label} (under L1: {self.current_question_level_1.label}) at y={q_line_y} due to new L2 start.")

                    label = number_str
                    level = 2
                    new_q_l2 = QuestionBase(label, self.current_page_number, level, q_line_x, q_line_y, self.page_width, self.page_height, q_line_h)
                    self.current_question_level_2 = new_q_l2
                    self.current_question_level_1.parts.append(new_q_l2)
                    print(f"Started Level 2 Sub-Part: {label} under Part {self.current_question_level_1.label} at y={q_line_y} on page {self.current_page_number}")
            
            self.processed_lines.append(assembled_line_sequence)
            self.current_line_symbols = []
            self.last_symbol_on_line = None

    def attach(self, page_width, page_height):
        super().attach(page_width, page_height)
        self.page_width = float(page_width)
        self.page_height = float(page_height)
        # print(f"QuestionDetectorV2 attached to page with width: {self.page_width} and height: {self.page_height}")

    def handle_sequence(self, seq: SymSequence, page: int):
        if page != self.current_page_number:
            self._process_buffered_line()  # Process any remaining symbols from the previous page
            self.current_page_number = page
            self.current_line_symbols = []
            self.last_symbol_on_line = None
            # print(f"QuestionDetectorV2 starting page {page}")

        for symbol in seq.data: # Assuming seq.data contains the list of Symbol objects
            if not self.current_line_symbols:
                self.current_line_symbols.append(symbol)
                self.last_symbol_on_line = symbol
            else:
                last_sym = self.last_symbol_on_line
                assert last_sym is not None # Should always be true if current_line_symbols is not empty

                # Vertical Alignment Check: symbol.y is top of the symbol
                vertically_aligned = abs(symbol.y - last_sym.y) <= self.VERTICAL_ALIGNMENT_TOLERANCE

                # Horizontal Proximity Check: symbol.x > last_sym.x and gap is within tolerance
                # Gap is symbol.x - (last_sym.x + last_sym.w)
                horizontally_proximate = (symbol.x > last_sym.x and
                                          (symbol.x - (last_sym.x + last_sym.w)) <= self.HORIZONTAL_PROXIMITY_TOLERANCE)

                if vertically_aligned and horizontally_proximate:
                    self.current_line_symbols.append(symbol)
                    self.last_symbol_on_line = symbol
                else:
                    # Symbol starts a new line
                    self._process_buffered_line()
                    self.current_line_symbols = [symbol]
                    self.last_symbol_on_line = symbol
        # print(f"QuestionDetectorV2 handled sequence on page {page}: {seq.get_text()}") # Original print removed

    def on_finish(self):
        self._process_buffered_line()  # Process any remaining symbols
        
        # Cascading finalization for any open questions/parts at the very end
        if self.current_question_level_0 is not None:
            final_y_coord = self.page_height # End at the bottom of the last page

            if self.current_question_level_2 is not None: # L2 was open
                self.current_question_level_2.y1 = final_y_coord
                # L2 should be in L1.parts
                print(f"Finalized Last Level 2: {self.current_question_level_2.label} (under L1: {self.current_question_level_1.label if self.current_question_level_1 else 'None'}) at end of page {self.current_page_number}")
            
            if self.current_question_level_1 is not None: # L1 was open
                self.current_question_level_1.y1 = final_y_coord
                # L1 should be in L0.parts
                print(f"Finalized Last Level 1: {self.current_question_level_1.label} (under L0: {self.current_question_level_0.label}) at end of page {self.current_page_number}")

            self.current_question_level_0.y1 = final_y_coord
            self.questions_list.append(self.current_question_level_0)
            print(f"Finalized Last Question: {self.current_question_level_0.label} at end of page {self.current_page_number if self.current_page_number != -1 else 'undefined'}")
            
        self.current_question_level_0 = None
        self.current_question_level_1 = None
        self.current_question_level_2 = None
        
        # print("QuestionDetectorV2 finishing up...")
        # For debugging:
        # print("All detected Level 0 Questions (QuestionBase objects):")
        # for q_base in self.questions_list:
        #     print(f"  Label: {q_base.label}, Page: {q_base.pages}, X: {q_base.x}, Y: {q_base.y}, Y1: {q_base.y1}, Height: {q_base.h}")


    def get_question_list(self, pdf_file_name_or_path) -> list[QuestionBase]: # Returning QuestionBase for now
        # This method will eventually use the processed lines to identify questions.
        # For now, it returns an empty list as per the original placeholder.
        # The task asks to return self.questions_list which contains QuestionBase objects.
        # Conversion to Question objects can be done here or by the caller if needed.
        # print(f"QuestionDetectorV2 returning {len(self.questions_list)} QuestionBase objects for {pdf_file_name_or_path}")
        return self.questions_list


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


if __name__ == "__main__":
    syms = SymSequence()
    for i in range(10):
        syms.append(Symbol(chr(i + 65), 0, 0, 10, 10))

    print(syms.size())
    print(syms[:6])
