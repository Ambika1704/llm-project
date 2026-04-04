from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import google.generativeai as genai
import pypdf
from io import BytesIO
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the Flask application
app = Flask(__name__)

# Enable CORS (Cross-Origin Resource Sharing) 
# This allows the frontend (e.g., Next.js running on port 3000) to communicate with this backend without security blocks.
CORS(app)

# Ollama API URL
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# System rules for formatting the LLM response
SYSTEM_PROMPT = (
    "\n"
    "GENERAL RULES\n"
    "\n"
    "- Use simple and clear language\n"
    "- Do NOT use markdown formatting (no **, no bullet points, no special symbols)\n"
    "- Keep answers clean and readable\n"
    "\n"
    "\n"
    "RESPONSE STYLE DETECTION\n"
    "\n"
    "Understand the user's intent from their question and respond accordingly:\n"
    "\n"
    "1. SHORT ANSWER:\n"
    "If the question includes words like:\n"
    '  "short", "brief", "in short", "summary", "quick"\n'
    "Then:\n"
    "- Answer in 2 to 3 lines only\n"
    "- Focus only on key idea\n"
    "\n"
    "2. DETAILED EXPLANATION:\n"
    "If the question includes words like:\n"
    '  "explain", "describe", "detail", "how", "why"\n'
    "Then:\n"
    "- Explain clearly in simple language\n"
    "- Use examples if needed\n"
    "- Keep it understandable\n"
    "\n"
    "3. EASY / BEGINNER MODE:\n"
    "If the question includes words like:\n"
    '  "simple", "easy", "for beginner", "like I\'m 5"\n'
    "Then:\n"
    "- Explain like teaching a beginner student\n"
    "- Use very simple words\n"
    "- Avoid technical terms\n"
    "\n"
    "\n"
    "DEFAULT BEHAVIOR\n"
    "\n"
    "If no specific style is mentioned:\n"
    "- Give a clear explanation in medium length (4-6 lines)\n"
    "\n"
    "\n"
    "OUTPUT\n"
    "\n"
    "Generate the answer based on the detected style from the user's question."
)

@app.route("/", methods=["GET"])
def index():
    """
    GET / API Endpoint
    A simple health check to verify the backend is running.
    """
    return jsonify({"message": "Flask Backend is running successfully! Use POST /generate to interact with the LLM."})

@app.route("/generate", methods=["POST"])
def generate():
    """
    POST /generate API Endpoint
    Expects a JSON payload: {"prompt": "your question or text"}
    
    This acts as a bridge to a locally running pre-trained LLM (LLaMA3 via Ollama).
    It DOES NOT train a model from scratch, but utilizes the already capable pre-trained model.
    """
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        user_prompt = data.get("prompt", "")
        req_model = data.get("model", "local")
        feature = data.get("feature", "chat")

        # Handle PDF Upload
        if not request.is_json and "file" in request.files:
            file = request.files["file"]
            if file.filename != '':
                file_bytes = file.read()
                if len(file_bytes) > 5 * 1024 * 1024:
                    return jsonify({"error": "File size exceeds 5MB limit."}), 400
                try:
                    reader = pypdf.PdfReader(BytesIO(file_bytes))
                    extracted_text = ""
                    for page in reader.pages:
                        extracted_text += page.extract_text() + "\n"
                    
                    # Truncate to reasonable limits to avoid context explosions
                    extracted_text = extracted_text[:30000]
                    user_prompt = f"Background Document Content:\n{extracted_text}\n\nUser Question/Request:\n{user_prompt}"
                except Exception as e:
                    return jsonify({"error": f"Failed to parse PDF: {str(e)}"}), 400

        if not user_prompt:
            return jsonify({"error": "Missing 'prompt' or document context"}), 400

        # System Prompt Routing for Study Modes
        if feature == "notes":
            active_system_prompt = (
                "You are an AI Study Assistant.\n"
                "Convert the provided text/conversation into structured study material.\n"
                "Output format:\n"
                "1. Detailed Notes: clear and well-explained notes. Cover all important concepts using examples.\n"
                "2. Bullet Points: key points in short and crisp format. Focus on important facts only.\n"
                "3. Short Summary: very concise summary (2-4 lines).\n"
                "Instructions: Keep language simple and easy to understand (student-friendly). Organize clearly with headings."
            )
        elif feature == "summarize":
            active_system_prompt = (
                "You are an AI Text Summarizer.\n"
                "Provide a precise, well-structured summary of the text provided by the user. "
                "Focus purely on the main ideas and crucial details. Avoid conversational filler."
            )
        else:
            active_system_prompt = SYSTEM_PROMPT

        if req_model == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                return jsonify({"error": "Gemini API key is missing. Please set the GEMINI_API_KEY environment variable."}), 400
            
            try:
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=active_system_prompt)
                response = model.generate_content(user_prompt)
                return jsonify({"response": response.text})
            except Exception as e:
                return jsonify({"error": f"Gemini API request failed: {str(e)}"}), 500

        # 2. Prepare the payload for Ollama
        ollama_payload = {
            "model": "llama3",
            "prompt": user_prompt,
            "system": active_system_prompt,
            "stream": False
        }

        # 3. Forward the request to Ollama
        try:
            response = requests.post(OLLAMA_API_URL, json=ollama_payload, timeout=300)
            response.raise_for_status() 
        except requests.exceptions.ConnectionError:
            return jsonify({
                "error": "Failed to connect to Ollama. Please ensure the Ollama application is running locally."
            }), 503
        except requests.exceptions.Timeout:
            return jsonify({
                "error": "Request to Ollama timed out. The model might be taking too long to respond."
            }), 504
        except requests.exceptions.RequestException as e:
            return jsonify({
                "error": f"An error occurred while communicating with Ollama: {str(e)}"
            }), 500

        # 4. Extract the generated text from Ollama's response
        ollama_data = response.json()
        generated_text = ollama_data.get("response", "")

        # 5. Return the JSON response back to the frontend
        return jsonify({
            "response": generated_text
        })

    except Exception as e:
        # Catch any other unexpected errors
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


if __name__ == "__main__":
    # Run the Flask app on localhost at port 5000
    # Enable debug mode for easier development
    app.run(host="0.0.0.0", port=5000, debug=True)
