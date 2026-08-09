import os
import requests
import json

def test_gemini_key():
    print("====================================================")
    print("          Aegis Gemini API Diagnosis Utility         ")
    print("====================================================\n")
    
    # Attempt to retrieve from environment first
    api_key = os.environ.get('GEMINI_API_KEY')
    
    if not api_key:
        print("💡 GEMINI_API_KEY environment variable not detected.")
        api_key = input("👉 Please paste your Gemini API Key to run diagnosis: ").strip()
        
    if not api_key:
        print("❌ Error: No API key provided.")
        return

    # Check key format
    obfuscated = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "invalid"
    print(f"\n🔑 Key Loaded: {obfuscated}")
    
    # Endpoint to test gemini-2.5-flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    body = {
        "contents": [{
            "parts": [{
                "text": "Say 'Aegis system is active and ready!' in a short and concise trading style sentence."
            }]
        }]
    }

    print("📡 Sending diagnostics payload to gemini-2.5-flash endpoint...")
    try:
        response = requests.post(url, headers=headers, json=body, timeout=12)
        
        print(f"🔄 HTTP Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result_data = response.json()
            try:
                content_text = result_data['candidates'][0]['content']['parts'][0]['text']
                print("\n✅ [SUCCESS] Your Gemini API key is valid and fully functional!")
                print("====================================================")
                print(f"Model Response: {content_text.strip()}")
                print("====================================================")
            except (KeyError, IndexError):
                print(f"\n⚠️  [WARNING] Connection succeeded but response format was unexpected. Raw response:")
                print(json.dumps(result_data, indent=2))
        elif response.status_code == 429:
            print("\n❌ [FAIL] Rate limit exceeded (HTTP 429).")
            print("   Please check if your AI Studio project has exceeded its quota limits or if you need to wait 1 minute for request cooldowns.")
            try:
                print(json.dumps(response.json(), indent=2))
            except ValueError:
                pass
        else:
            print(f"\n❌ [FAIL] API request rejected (HTTP {response.status_code})")
            print("   Please check if the API key is correct or has expired.")
            try:
                error_details = response.json()
                print("Error Response:")
                print(json.dumps(error_details, indent=2))
            except ValueError:
                print(f"Raw Text Response: {response.text}")
                
    except requests.exceptions.RequestException as e:
        print(f"\n❌ [FAIL] Network connection failed: {str(e)}")
        print("   Please verify your internet connection or proxy settings.")

if __name__ == '__main__':
    test_gemini_key()
