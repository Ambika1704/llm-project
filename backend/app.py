from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

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
        # 1. Parse the incoming JSON from the frontend request
        data = request.get_json()
        
        # Verify that prompt was provided
        if not data or "prompt" not in data:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400
            
        user_prompt = data["prompt"]

        # 2. Prepare the payload for Ollama
        # We specify the model as "llama3", pass the prompt, and set stream to False
        # so we get the entire response at once. We also pass the system prompt for formatting.
        ollama_payload = {
            "model": "llama3",
            "prompt": user_prompt,
            "system": SYSTEM_PROMPT,
            "stream": False
        }

        # 3. Forward the request to Ollama
        try:
            # We increase the timeout to 300 seconds (5 minutes) because 
            # local LLMs can sometimes take a while to generate text, especially on CPUs.
            response = requests.post(OLLAMA_API_URL, json=ollama_payload, timeout=300)
            response.raise_for_status() # Raise an exception for HTTP errors
        except requests.exceptions.ConnectionError:
            # Handle cases where Ollama is not running
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
