from numpy import column_stack
import requests
import time
import os
from os.path import sep
import json


os.environ

app_id = os.environ["MATHPIX_APPID"]
api_key = os.environ["MATHPIX_APIKEY"]


def ocr_image(filepath):
    basename = os.path.basename(filepath)
    r = requests.post(
        "https://api.mathpix.com/v3/text",
        files={"file": open(filepath, "rb")},
        data={
            "options_json": json.dumps(
                {
                    "math_inline_delimiters": ["$", "$"],
                    # "math_display_delimiters": ["$$", "$$"],
                    "include_line_data": True,
                    "formats": ["text", "latex_styled"],
                    "tags": [basename, "igcse", "test"],
                    "data_options": {"include_latex": True},
                }
            )
        },
        headers={"app_id": app_id, "app_key": api_key},
    )
    with open(f"output{sep}{basename}.json", "w", encoding="utf-8") as f:
        dump = json.dumps(r.json(), indent=4, sort_keys=True)
        print(dump)
        f.write(dump)


def get_latex(imagepath):
    basename = os.path.basename(imagepath)  # "9702_m23_qp_22.png"
    jsonpath = f"output{sep}{basename}.json"
    mdpath = f"output{sep}{basename}.md"
    with open(jsonpath, "r", encoding="utf-8") as f:
        tex = json.loads(f.read()).get("text")
        # print(tex)
        with open(mdpath, "w", encoding="utf-8") as f2:
            f2.write(tex)
            return tex


def convert_mmd_to_pdf(imagepath):

    mmd = get_latex(imagepath)
    url = "https://api.mathpix.com/v3/converter"
    payload = json.dumps({"mmd": mmd, "formats": {"pdf": True}})
    headers = {
        "app_id": app_id,
        "app_key": api_key,
        "Content-Type": "application/json",
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    conversion_id = response.json().get("conversion_id")
    done = False
    while not done:
        res = requests.get(
            url=f"https://api.mathpix.com/v3/converter/{conversion_id}",
            headers=headers,
        ).json()
        stat = res.get("status")
        con_stat = res.get("conversion_status")
        if stat != "completed" or not con_stat:
            print("Waiting : 1")
            time.sleep(1)
            print(json.dumps(res, indent=4))
            continue
        if con_stat.get("pdf", {}).get("status") != "completed":
            print("Waiting : 2")
            time.sleep(1)
            continue
        done = True

    url = "https://api.mathpix.com/v3/converter/" + conversion_id + ".pdf"
    response = requests.get(url, headers=headers)
    with open(f"output{sep}{os.path.basename(imagepath)}" + ".pdf", "wb") as f:
        f.write(response.content)


if __name__ == "__main__":
    imagepath = f"output{sep}9702_m23_qp_22.png"
    convert_mmd_to_pdf(imagepath)
    # get_latex(imagepath)
    # ocr_image(imagepath)
