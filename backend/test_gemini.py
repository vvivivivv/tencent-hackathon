import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_conversion_rate(segment: str) -> str:
    """Returns the current conversion rate for a customer segment.

    Args:
        segment: e.g. 'mobile_first_time', 'desktop_returning'
    """
    # stub implementation for initial testing
    fake_data = {"mobile_first_time": "34%", "desktop_returning": "71%"}
    return fake_data.get(segment, "unknown segment")

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="What's the conversion rate for mobile first-time customers, and is that concerning?",
    config=types.GenerateContentConfig(tools=[get_conversion_rate]),
)
print(response.text)

