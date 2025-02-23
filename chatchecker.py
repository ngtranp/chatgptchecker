import json
import os
import openai
import dotenv
import requests

dotenv.load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# JSON_FILE_PATH = "scrapy2/DeadLinkChecker/multi_link_statistics.json"
JSON_FILE_PATH = "test_data.json"

def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)

def extract_dead_links(data):
    dead_links = []

    if data["summary"]["client_errors"] > 0 or data["summary"]["server_errors"] > 0 or data["summary"]["unknown_responses"] > 0:
        for category in ["4xx", "5xx"]:
            if category in data["link_statistics"]:
                for link in data["link_statistics"][category]["urls"]:
                    dead_links.append({"url": link["url"], "found_on": link["found_on"]})

    return dead_links

def check_url_status(url):
    """Check if the suggested correction or alternative link returns a 200 OK response."""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def chatgpt_verify(dead_links):
    if not dead_links:
        return {"message": "No broken links found"}
    
    prompt = f"""
    The following links are broken. Analyze them and provide a **concise** reason for failure.
    
    {json.dumps(dead_links, indent=2)}

    1. **Language Verification**: Detect the primary language of the URL.
    2. **Morphological & Inflection Analysis**: Identify if the last word in the URL is an inflected form.
    3. **Typo & Similarity Detection**: If a word is **slightly misspelled**, suggest a correction.
    4. **Alternative Page Path Analysis**:
       - Compare the last segment of the URL (after the last `/`) with common webpage names.
       - Example: "browser.html" should suggest checking "browse.html".
       - Example: "index.htm" should suggest "index.html".
       - Example: "categorys" should suggest "categories".
    5. **Correction**: Suggest the correct form **only if it has a strong match**.
    6. **Alternative URLs**: Suggest an alternative page **if the correction does not exist**.
    7. **Manual Check**: If the issue is unclear, return "Manual check required".
    
    **IMPORTANT:** Respond **only** with valid JSON. Do **not** include any explanations or extra text.

    **Return JSON format:**
    {{
      "original_url": (string),
      "detected_language": (string),
      "suggested_correction": (string or null),
      "alternative_forms_checked": (list of strings),
      "verified_working_url": (string or null),
      "analysis": (short explanation),
      "manual_check_required": (true/false)
    }}
    """

    client = openai.OpenAI()
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a web path analyzer. Detect spelling errors and suggest common alternatives for broken URLs. Ensure your response is valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        # Debugging: Print the raw response
        print("DEBUG: Full ChatGPT Response:", response)

        if not response or not response.choices:
            return {"error": "No response from ChatGPT"}

        chatgpt_content = response.choices[0].message.content.strip()
        if not chatgpt_content:
            return {"error": "Empty response from ChatGPT"}

        # Validate if the response is in JSON format
        try:
            parsed_response = json.loads(chatgpt_content)
            return parsed_response
        except json.JSONDecodeError:
            return {"error": "ChatGPT did not return valid JSON"}

    except Exception as e:
        return {"error": f"ChatGPT API call failed: {str(e)}"}

def store_results_locally(results):
    """Temporary function to store results locally instead of a database."""
    print("Skipping database storage for now. Here are the results:")
    print(json.dumps(results, indent=2))

def main():
    data = load_json(JSON_FILE_PATH)
    dead_links = extract_dead_links(data)
    chatgpt_response = chatgpt_verify(dead_links)

    # Ensure valid JSON response
    if isinstance(chatgpt_response, dict) and "error" not in chatgpt_response:
        chatgpt_parsed = chatgpt_response
    else:
        chatgpt_parsed = {"error": "Invalid JSON response from ChatGPT"}

    # Verify if suggested correction is a working URL
    if chatgpt_parsed.get("suggested_correction"):
        corrected_url = chatgpt_parsed["suggested_correction"]
        if check_url_status(corrected_url):
            chatgpt_parsed["verified_working_url"] = corrected_url
        else:
            chatgpt_parsed["verified_working_url"] = None

    final_results = {"error_found": chatgpt_parsed}

    store_results_locally(final_results)  

if __name__ == "__main__":
    main()
