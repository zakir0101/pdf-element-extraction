try:
    import cairo
except ModuleNotFoundError:
    print("WARNING: Cairo module not found in core_models. Some functionalities may be limited.")
    cairo = None # Define cairo as None so type hints and later references don't fail immediately

from typing import Any # Import Any for type hinting
import numpy as np  # speeds things up; pure-Python fallback shown later
from engine.pdf_utils import all_subjects, _surface_as_uint32
from collections import defaultdict
import json
from os.path import sep
import os

# ********************************************************************
# ********************* Detecotr Data-classes


class Box:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.box = (x, y, x + w, y + h)
        pass

    def __str__(
        self,
    ):
        return f"Box(x={self.x}, y={self.y}, w={self.w}, h={self.h})"

    def get_box(self):
        return self.box

    def __set_box__(
        self,
    ):
        self.box = (self.x, self.y, self.x + self.w, self.y + self.h)


class Symbol(Box):
    def __init__(self, ch, x, y, w, h) -> None:
        super().__init__(x, y, w, h)
        self.ch = ch
        self.threshold_y = 0.45 * h
        self.threshold_x = 0.45 * w
        self.box: tuple | None = None
        self.__set_box__()
        pass

    def __str__(
        self,
    ):
        return f"Smybole({self.ch}, x={self.x}, y={self.y}, w={self.w}, h={self.h})"

    def __set_box__(
        self,
    ):
        self.box = self.x, self.y - self.h, self.x + self.w, self.y

    def is_connected_with(self, s2):
        s2: Symbol = s2
        diff1 = abs(s2.x + s2.w - self.x)
        diff2 = abs(s2.x - self.x + self.w)
        inner_diff = min(diff1, diff2)
        return inner_diff < self.threshold_x or inner_diff < s2.threshold_x


class BoxSegments(Box):

    def __init__(self, segments: list[Box]) -> None:
        if not segments:
            raise Exception("empty segments")
        self.data: list[Box] = segments.copy()
        self.__set_box__()
        # self.threshold_y = 0.3 * (self.box[-1] - self.box[1])
        # self.threshold_x = 0.3 * (self.box[-2] - self.box[0])

    def __getitem__(self, index) -> Symbol:
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def size(self):
        return self.data.__len__()

    def __str__(self) -> str:
        rep = f"{type(self).__name__}(lenght={len(self.data)}) =>\n"
        for it in self.data:
            rep += "   " + str(it) + "\n"
        return rep

    def __set_box__(self):
        x0, y0, x1, y1 = self.data[0].get_box()
        for d in self.data[1:]:
            nx0, ny0, nx1, ny1 = d.get_box()
            x0 = min(x0, nx0)
            y0 = min(y0, ny0)
            x1 = max(x1, nx1)
            y1 = max(y1, ny1)
        self.box = (x0, y0, x1, y1)
        self.x = x0
        self.y = y0
        self.w = x1 - x0
        self.h = y1 - y0


class SymSequence(BoxSegments):

    def __init__(self, symboles: list[Symbol]) -> None:
        if not symboles:
            raise Exception("empty Sequence")
        super().__init__(symboles)
        self.mean = (0, 0)
        self.data: list[Symbol] = self.data
        self.__set_mean__(self.box)
        self.threshold_y = 0.3 * (self.box[-1] - self.box[1])
        self.threshold_x = 0.3 * (self.box[-2] - self.box[0])
        pass

    def iterate_split(self, char: str = " "):
        sub = []
        for sym in self.data:
            if sym.ch in char:
                if len(sub) > 0:
                    yield SymSequence(sub)
                sub = []
            else:
                sub.append(sym)

        if len(sub) > 0:
            yield SymSequence(sub)

    def get_text(self, verbose=True) -> str:
        rep = ""
        for sym in self.data:
            rep += sym.ch
        if verbose:
            return f"Sequence(lenght={len(self.data)}, content={rep}, box={self.box})"
        else:
            return rep

    # def __set_box__(self):
    #     if len(self.box) == 0:
    #         return
    #     x0, y0, x1, y1 = self.data[0].get_box()
    #     for d in self.data[1:]:
    #         nx0, ny0, nx1, ny1 = d.get_box()
    #         x0 = min(x0, nx0)
    #         y0 = min(y0, ny0)
    #         x1 = max(x1, nx1)
    #         y1 = max(y1, ny1)
    #     self.box = (x0, y0, x1, y1)
    #     self.x = x0
    #     self.y = y0
    #     self.w = x1 - x0
    #     self.h = y1 - y0

    def __set_mean__(self, box):
        x0, y0, x1, y1 = box
        self.mean = []
        self.mean.append((x0 + x1) / 2)
        self.mean.append((y0 + y1) / 2)

    def row_align_with(self, seq_other):
        seq_other: SymSequence = seq_other
        return (
            abs(self.mean[1] - seq_other.mean[1]) < self.threshold_y
            or abs(self.box[-1] - seq_other.box[-1]) < self.threshold_y
        )

    def column_align_with(self, seq_other):
        seq_other: SymSequence = seq_other
        return (
            abs(self.mean[0] - seq_other.mean[0]) < self.threshold_x
            or abs(self.box[0] - seq_other.box[0]) < self.threshold_x
        )


class SurfaceGapsSegments(BoxSegments):

    def __init__(
        self, surface: "cairo.ImageSurface" if cairo else Any, gap_factor: float = 0.5
    ) -> None:
        """factor: a float number which will multiply (0.01 * page_height ) and be used
        as min empty gap (gap = number of sequencially empty/white rows of pixel) that should be skipped ...
        factor == 0     => then every line will be in its own seqment
        factor == 100   => the whole page will be treated as one segment
        """
        self.surface = surface
        s_height = surface.get_height()
        self.net_height = s_height
        self.empty_segments: list[Box] = []
        self.non_empty_segments: list[Box] = []
        self.gap_factor = gap_factor
        self.d0 = s_height * 0.01
        self.MIN_GAP_HEIGHT = self.gap_factor * self.d0

        self.find_empty_gaps(0)
        self.non_empty_segments, self.net_height = self.get_non_empty_gaps(
            0, s_height
        )

        if not self.non_empty_segments:
            raise Exception("THe Page is completly Empty !!")

        self.data = self.non_empty_segments
        self.__set_box__()

        # segments = get_segments( 0, s_height, d0, factor=gap_factor)
        # out_height += sum(seg_h + 2 * d2 for _, seg_h, d2 in segments)

    def find_empty_gaps(self, min_y=0):
        surface = self.surface
        mask = self.build_blank_mask(surface)
        gaps: list[Box] = []
        h_px = len(mask)
        MIN_COUNT = round(0.1 * self.d0)
        start = None
        not_blanck_count = 0
        blanck_count = 0
        is_blank_mode = True
        start = min_y
        for y, blank in enumerate(mask):
            if blank:
                blanck_count += 1
                not_blanck_count = 0
            else:
                not_blanck_count += 1
                blanck_count = 0

            if blanck_count > MIN_COUNT:
                is_blank_mode = True
            elif not_blanck_count > MIN_COUNT:
                is_blank_mode = False

            if is_blank_mode and start is None:
                start = y
            elif not is_blank_mode and start is not None:
                gaps.append(Box(0, start, surface.get_width(), y - start))
                start = None
        if start is not None:  # ran off bottom still in blank
            gaps.append(Box(0, start, surface.get_width(), h_px - start))

        fgaps = [
            box
            for box in gaps
            if box.h > self.MIN_GAP_HEIGHT and box.y >= min_y
        ]
        self.empty_segments = fgaps

    def get_non_empty_gaps(self, min_y, max_y):
        segments = []
        cursor = min_y
        net_height = 0
        for box in self.empty_segments:
            gy, gh = box.y, box.h
            if gy > cursor:
                h_curr = gy - cursor
                segments.append(
                    Box(0, cursor, self.surface.get_width(), h_curr)
                )
                net_height += h_curr
            cursor = gy + gh

        if cursor < max_y:  # rows after the last gap
            h_curr = max_y - cursor
            segments.append(Box(0, cursor, self.surface.get_width(), h_curr))
            net_height += h_curr

        if net_height < self.surface.get_height() - 2 * self.d0:
            net_height += 2 * self.d0

        return segments, net_height

    def filter_question_segments(self, min_y, max_y, page_range, curr_page):
        q_segs = []
        y0, y1 = 0, self.surface.get_height()
        if page_range[0] == curr_page:
            y0 = min_y - 1.5 * self.d0  # q.h
        if page_range[-1] == curr_page:
            y1 = max_y - 1.5 * self.d0  # q.h
        # print(y0, "   ", y1, "for debugging")
        # print("seq length = ", len(segments))
        for box in self.non_empty_segments:
            sy0, sy1, d0 = box.y, box.h + box.y, self.d0
            # if not self.default_d0 and d0:
            #     self.default_d0 = d0
            if y0 <= sy0 <= y1 or y0 <= sy1 <= y1:
                q_segs.append(box)
        ###: create a GapSegment obj
        # q_segs_obj: SurfaceGapsSegments = somefunction(q_segs)  # TODO:

        return q_segs

    def build_blank_mask(self, surface):
        pix = _surface_as_uint32(surface)
        w = surface.get_width()
        return np.fromiter(
            (self.row_is_blank(r, w) for r in pix),
            dtype=bool,
            count=pix.shape[0],
        )

    OPAQUE_WHITE = 0xFFFFFFFF
    ANY_ALPHA0_WHITE = 0x00FFFFFF  # alpha 0 + white RGB

    def row_is_blank(
        self, row, usable_cols, white=OPAQUE_WHITE, twhite=ANY_ALPHA0_WHITE
    ):
        part = row[:usable_cols]
        f1 = 0.15
        s_left = round(f1 * usable_cols)
        s_right = round((1 - f1) * usable_cols)
        middle = part[s_left:s_right]
        sides = np.concatenate((part[:s_left], part[s_right:]), axis=0)
        is_side_almost_empty = (
            np.count_nonzero((sides == white) | (sides == twhite)) / len(sides)
        ) > 0.99
        is_middle_completly_empyty = np.all(
            (middle == white) | (middle == twhite)
        )

        return is_middle_completly_empyty and is_side_almost_empty

    def clip_segments_from_surface_into_contex(
        self,
        out_ctx: "cairo.Context" if cairo else Any,
        out_y_start: float,
        segments: list[Box] | None = None,
        line_height: float | None = None,
    ):
        """return (y_after) the y-location after drawing the segments into the output Context"""
        if not segments:
            """use the whole page segments"""
            segments = self.non_empty_segments

        segments: "SurfaceGapsSegments" = segments # This is a self-reference essentially, or a forward one. String is safest.
        input_surf: "cairo.ImageSurface" if cairo else Any = self.surface

        # TODO: FIX ME FOR FULL PAGE RENDERING , the line_height is independent of page_height , following line should be change
        # for instande by adding a char_height (d0) to Box class
        if not line_height:
            line_height = self.d0
        for i, box in enumerate(segments):
            # box : Box = box
            src_y, seg_h = box.y, box.h
            """subtract 0.20 , why ?? 0.1 for shifting by 0.1 * h0 pixel , because the detecting 
            has some delayed response by this ammount , and +0.1 for padding"""
            y0 = round(src_y - 0.20 * line_height)
            """only the 0.2 correspond to the padding , so in practice we shift up by 0.1 and padd by 0.1 from up and down"""
            h0 = round(seg_h + 0.20 * line_height)  # + factor * d0
            # print(y0, y1, d0)

            sub = input_surf.create_for_rectangle(
                0, y0, input_surf.get_width(), h0
            )
            """Read the doc string below : this is for padding the top most line from above"""
            if out_y_start == 0:
                out_y_start = out_y_start + (1 * line_height)
            out_ctx.set_source_surface(sub, 0, out_y_start)
            out_ctx.paint()
            """this 0.25 is for spacing between lines, it require the surface to
            be paint white at beginning"""
            out_y_start += h0 + (0.55 * line_height)

        return out_y_start


# **************************************************************************
# ***********************  Gui/api Classes


class Chapter:
    def __init__(
        self,
        name: str,
        nr: int,
        description: str,
        embd: list[int] | None = None,
    ) -> None:
        self.name = name
        self.number = nr
        self.description = description
        self.embd = embd
        pass


class Paper:
    def __init__(self, name: str, nr: int, chapters: list[Chapter]) -> None:
        self.chapters = chapters
        self.name = name
        self.number = nr
        pass


class Subject:
    def __init__(self, id: str) -> None:
        if id not in all_subjects:
            raise Exception(f"Unsupported subject {id}")
        self.name: str = ""
        self.id = id
        self.papers: dict[int, Paper] = {}
        sub_path = f".{sep}resources{sep}syllabuses-files{sep}{id}.json"
        if not os.path.exists(sub_path):
            raise Exception(
                "somehow syllabus files for subject {id} could not be found !!"
            )
        self.load_subject_from_file(sub_path)

        pass

    def load_subject_from_file(self, file_path: str):
        f = open(file_path, "r", encoding="utf-8")
        content = f.read()
        raw_json = json.loads(content)
        # NOTE: remove me later
        if not isinstance(raw_json, list):
            raise Exception(f"Invalid subject file {file_path}")

        paper_to_chapters_dict: dict[int, list] = defaultdict(list)
        paper_to_pnames_dict: dict[int, str] = defaultdict(str)
        for item in raw_json:
            paper_to_key: dict[str, list[str]] = item["paper_to_key"]
            all_papers_numbers: list[int] = item["papers"]
            g_name = item.get("name", "")
            for p in all_papers_numbers:
                paper_to_pnames_dict[p] += g_name
            chapters: list[dict] = item["chapters"]
            for chap in chapters:
                chap_name: str = chap["name"]
                chap_nr: int = chap["number"]
                for nr_str, identifier_str_list in paper_to_key.items():
                    chap_paper_nrs = list(map(int, nr_str.split(",")))
                    description = self.__resolve_description_from_chapter(
                        identifier_str_list, chap
                    )
                    chapter_obj = Chapter(chap_name, chap_nr, description)
                    for paper_nr in chap_paper_nrs:
                        paper_to_chapters_dict[paper_nr].append(chapter_obj)

        for p_nr, chps in sorted(
            paper_to_chapters_dict.items(), key=lambda x: x[0]
        ):
            self.papers[p_nr] = Paper(paper_to_pnames_dict[p_nr], p_nr, chps)

    def __resolve_description_from_chapter(
        self, identifier_str_list: list[str], chap: dict
    ) -> str:
        # do something , combin
        description = ""
        for identifier_str in identifier_str_list:
            ident_split = identifier_str.split(".")
            last_key_names = ident_split[-1]
            nested_keys = ident_split[:-1]
            description += self.__resolve_description_from_list_of_keys(
                nested_keys, last_key_names, chap
            )
        return description

    def __resolve_description_from_list_of_keys(
        self, nested_keys: list[str], last_key_names: str, chap: dict, depth=0
    ):
        desc = ""
        if nested_keys:
            for i, nested in enumerate(nested_keys):
                if not chap.get(nested, []):
                    continue
                for sub_chap in chap[nested]:
                    desc += self.__resolve_description_from_list_of_keys(
                        nested_keys[i + 1 :],
                        last_key_names,
                        sub_chap,
                        depth + 1,
                    )
        else:
            desc += self.__resolve_description_from_chapter_last_key(
                last_key_names, chap, depth
            )

        return desc

    def __resolve_description_from_chapter_last_key(
        self, last_keys: str, chap: dict, depth=0
    ):
        desc = ""
        for key in last_keys.split(","):
            if not chap.get(key, ""):
                continue
            name = key
            if key != "examples":
                name = (
                    chap.get("name") + f"({key})"
                    if (depth > 0 and "name" in chap)
                    else key
                )
            desc += f"\n\n**{name}**:\n\n" + chap.get(key, "")
        return desc
