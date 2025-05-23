from engine.pdf_utils import igcse_path, all_subjects
from collections import defaultdict
import json
from engine.pdf_detectors import Question
from os.path import sep
import os


class QuestionItem(Question):
    def __init__(
        self,
    ) -> None:
        pass


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
