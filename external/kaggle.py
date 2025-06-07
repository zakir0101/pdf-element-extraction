"""
!pip install -U "magic-pdf[full]"
!pip install flask pyngrok


!pip install huggingface_hub
!wget https://github.com/opendatalab/MinerU/raw/master/scripts/download_models_hf.py -O download_models_hf.py
!python download_models_hf.py


"""

import os
from os.path import sep
import fitz
from PIL import Image
from flask import Flask, request, jsonify
from pyngrok import ngrok
from kaggle_secrets import UserSecretsClient

from magic_pdf.data.data_reader_writer import (
    FileBasedDataWriter,
    FileBasedDataReader,
)
from magic_pdf.data.dataset import ImageDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.data.read_api import read_local_images
from magic_pdf.operators.models import InferenceResult, PipeResult


# --- 1. SETUP THE TUNNEL ---
# Authenticate ngrok using the secret you stored
user_secrets = UserSecretsClient()
ngrok.set_auth_token(user_secrets.get_secret("NGROK_AUTH_TOKEN"))

# Open a tunnel to the Flask app port (we'll use 5000)
public_url = ngrok.connect(5000)
print(f"✅ Kaggle is now live at: {public_url}")


# --- 2. LOAD YOUR HEAVY MODEL (DO THIS ONLY ONCE) ---
# This is where you would load your model, weights, etc.
# Example:
# from your_module import load_model, predict_function
# model = load_model('/kaggle/input/my-repo-name/models/best_model.pth')
print("✅ Model loaded successfully (this is a placeholder).")


def detect_layout_miner_u_online(img_bytes: bytes, data: dict):

    from magic_pdf.data.data_reader_writer import (
        FileBasedDataWriter,
        FileBasedDataReader,
    )

    from flask import send_file

    exam = data.get("exam", "")
    d_mode = data.get("display-mode", "")
    nr = "nr" + str(data.get("number", 0))
    want = data.get("want", "content.md")

    key = exam + d_mode
    f_dir = sep.join([".", key])
    os.makedirs(f_dir, exist_ok=True)
    f_path = f"{f_dir}{sep}{nr}{want}"

    if not os.path.exists(f_path):
        print("ocring ....")
        local_image_dir, local_md_dir = f"{f_dir}{sep}{nr}images", f_dir
        image_dir = str(os.path.basename(local_image_dir))

        os.makedirs(local_image_dir, exist_ok=True)

        image_writer, md_writer = FileBasedDataWriter(
            local_image_dir
        ), FileBasedDataWriter(local_md_dir)

        lang = "ch_lite"
        ds = ImageDataset(img_bytes, lang=lang)

        inf_res: InferenceResult = ds.apply(
            doc_analyze,
            ocr=True,
            lang=lang,
            show_log=True,
        )

        pip_res: PipeResult = inf_res.pipe_ocr_mode(image_writer, lang=lang)

        # p1 =  f"{f_dir}{sep}content.md"
        pip_res.dump_md(md_writer, f"{nr}content.md", image_dir)

        p2 = f"{f_dir}{sep}{nr}draw2.png"
        pip_res.draw_layout(p2)
        pdf_to_png(p2)

        p3 = f"{f_dir}{sep}{nr}draw3.png"
        pip_res.draw_span(p3)
        pdf_to_png(p3)

        p4 = f"{f_dir}{sep}{nr}draw4.png"
        pip_res.draw_line_sort(p4)
        pdf_to_png(p4)
    else:
        print("using cached version")

    return send_file(f_path, as_attachment=True)


def pdf_to_png(pdf_path):

    dpi = 150
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=dpi)
    mode = "RGBA" if pix.alpha else "RGB"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    doc.close()
    img.save(pdf_path, "png")


# --- 3. CREATE THE FLASK APP ---
app = Flask(__name__)


@app.route("/", methods=["GET"])
def say_hallo():
    return jsonify({"message": "hallo zakir"})


@app.route("/predict", methods=["POST"])
def predict():
    """The main endpoint for your GUI to call."""
    try:
        # Assuming the GUI sends an image file
        image_file = request.files["image"]
        image_bytes = image_file.read()
        print(request.form)
        return detect_layout_miner_u_online(image_bytes, request.form)

        # Return the result as JSON
        # return jsonify({"message":"hallo zakir"})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


# This will run the Flask app and keep the notebook cell running.
app.run(port=5000)
