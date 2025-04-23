from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from PIL import Image, ImageEnhance
import base64
import io
import re

app = Flask(__name__)
CORS(app)

OPENROUTER_API_KEY = "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"

@app.route("/processScorecardGPT", methods=["POST"])
def extract_scores():
    if "image" not in request.files:
        return jsonify({"error": "Missing image"}), 400

    image_file = request.files["image"]

    # Convert and enhance image
    image = Image.open(image_file.stream).convert("RGB")
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode()


    # 🧠 Full Player Prompt
    prompt = """
        You are a golf scorecard assistant.

        The user uploaded a scorecard image with handwritten scores. Each player (A–D) has their own row marked by a capital letter (e.g., “A”), followed by two rows labeled "Score" and "Result".

        ✅ Important:
        - Carefully distinguish between digits like 8 and 3.
        - Carefully distinguish between digits like 6 and 4.
        - Only extract clearly written numbers from the "Score" row.
        - Do not guess — only include values that are clearly visible and legible.
        - Do not use values from the “Result” row.
        - Do NOT infer data. If a row is blank or unreadable, say "No scores for Player X".

        🎯 For each Player A, B, C, and D:
        1. Extract the handwritten numeric scores from the “Score” row, for holes 1–18.
        2. Return Out total (sum of holes 1–9) and In total (sum of 10–18).
        3. If there are no scores, just return: "Scores for Player X:"  
        
        Ensure all 18 handwritten scores are listed — even if some are unreadable, skip them but keep the count aligned to 18 holes.

        📌 Return exactly in this format:

        Scores for Player A: 4, 5, 3, ..., 5
        Out: 37
        In: 42

        Scores for Player B:
        Scores for Player C: 5, 6, ...
        Out: 39
        In: 45

        ... etc.

        No extra commentary.
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    { "type": "text", "text": prompt },
                    { "type": "image_url", "image_url": { "url": f"data:image/png;base64,{image_base64}" } }
                ]
            }
        ],
        "max_tokens": 800
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if response.status_code != 200:
            return jsonify({ "error": f"OpenRouter error: {response.status_code}", "details": response.text }), 500

        content = response.json()["choices"][0]["message"]["content"]
        print("\n🔍 RAW RESPONSE FROM OPENAI:\n", content)

        result = {}

        for letter in ['A', 'B', 'C', 'D']:
            scores_match = re.search(rf"Scores for Player {letter}:\s*([\d,\s]*)", content)
            out_match = re.search(rf"Out:\s*(\d+)?", content.split(f"Scores for Player {letter}:")[1])
            in_match = re.search(rf"In:\s*(\d+)?", content.split(f"Scores for Player {letter}:")[1])

            if scores_match:
                scores_raw = scores_match.group(1)
                scores = [s.strip() for s in scores_raw.split(",") if s.strip().isdigit()]
            else:
                scores = []

            out = int(out_match.group(1)) if out_match and out_match.group(1) else None
            in_total = int(in_match.group(1)) if in_match and in_match.group(1) else None

            result[letter] = {
                "scores": scores[:18],
                "out": out,
                "in": in_total,
            }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": f"Failed to parse response: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
