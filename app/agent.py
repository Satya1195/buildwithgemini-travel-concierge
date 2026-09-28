# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from google.cloud import firestore
from google.genai import types

from .a2ui_utils import a2ui_callback


# CRITICAL: Hardcode project ID and bucket name as strings.
# On Agent Platform, google.auth.default() returns project number which breaks Firestore/Storage.
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-7ce6bb053187"
GCS_BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-01-7ce6bb053187"
MEMORY_BANK_ID = "7766024349819076608"


_default_memory_service = None


def memory_bank_service_builder():
    global _default_memory_service
    if _default_memory_service is None:
        _default_memory_service = VertexAiMemoryBankService(
            project=FIRESTORE_PROJECT_ID,
            location="us-east1",
            agent_engine_id=MEMORY_BANK_ID,
        )
    return _default_memory_service


class AutoMemoryPreloadTool(PreloadMemoryTool):
    async def process_llm_request(self, *, tool_context, llm_request):
        if getattr(tool_context._invocation_context, "memory_service", None) is None:
            tool_context._invocation_context.memory_service = memory_bank_service_builder()
        await super().process_llm_request(tool_context=tool_context, llm_request=llm_request)


async def generate_memories_callback(callback_context: CallbackContext):
    if getattr(callback_context._invocation_context, "memory_service", None) is None:
        callback_context._invocation_context.memory_service = memory_bank_service_builder()
    await callback_context.add_session_to_memory()
    return None



# Load sandbox or agent engine resource name from deployment_metadata.json
deployment_meta_path = Path(__file__).parent.parent / "deployment_metadata.json"
sandbox_resource_name = None
agent_engine_resource_name = None

if deployment_meta_path.exists():
    try:
        with open(deployment_meta_path) as f:
            meta = json.load(f)
            sandbox_resource_name = meta.get("sandbox_resource_name")
            agent_engine_resource_name = meta.get("remote_agent_runtime_id")
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name=sandbox_resource_name,
    agent_engine_resource_name=agent_engine_resource_name,
)

# Lazy or direct client instantiation with hardcoded project ID
db = firestore.Client(project=FIRESTORE_PROJECT_ID)
destinations_ref = db.collection("destinations")




def get_weather(query: str) -> str:
    """Simulates getting weather information for a location.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    elif "tokyo" in query.lower():
        return "It's 72 degrees and clear."
    elif "paris" in query.lower():
        return "It's 65 degrees and pleasant."
    return "It's 75 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    elif "tokyo" in query.lower():
        tz_identifier = "Asia/Tokyo"
    elif "paris" in query.lower():
        tz_identifier = "Europe/Paris"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def list_destinations(category: str = None) -> list:
    """Retrieves travel destinations stored in Firestore database.

    Args:
        category: Optional category filter string (e.g., 'Culture & Technology', 'Romance & Art').

    Returns:
        A list of destination dictionaries.
    """
    results = []
    if category:
        query_ref = destinations_ref.where("category", "==", category)
        docs = query_ref.stream()
    else:
        docs = destinations_ref.stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    return results


def get_destination_details(destination_id: str) -> dict:
    """Retrieves details of a specific destination from Firestore by ID.

    Args:
        destination_id: Unique destination string identifier (e.g. 'tokyo', 'paris', 'kyoto').

    Returns:
        A dictionary containing destination details or error details.
    """
    doc_ref = destinations_ref.document(destination_id.lower().strip())
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return {"error": f"Destination with ID '{destination_id}' not found."}


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    category: str,
    description: str,
    rating: float,
    average_cost_per_day: float,
    tags: str,
) -> str:
    """Adds a new destination or updates an existing one in the Firestore database.

    Args:
        destination_id: Unique string identifier (e.g., 'rome').
        name: Name of the destination (e.g., 'Rome').
        country: Country (e.g., 'Italy').
        category: Category (e.g., 'History & Food').
        description: Summary description of the location.
        rating: Rating out of 5.0.
        average_cost_per_day: Estimated cost per day in USD.
        tags: Comma-separated tags string (e.g., 'colosseum, food, history').

    Returns:
        A success string confirmation.
    """
    doc_id = destination_id.lower().strip()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    item = {
        "id": doc_id,
        "name": name,
        "country": country,
        "category": category,
        "description": description,
        "rating": float(rating),
        "average_cost_per_day": float(average_cost_per_day),
        "tags": tag_list,
    }
    destinations_ref.document(doc_id).set(item)
    return f"Successfully saved destination '{name}' ({doc_id}) to Firestore."


def calculate_trip_budget(destination_id: str, days: int, travelers: int = 1) -> dict:
    """Calculates estimated total trip budget based on destination daily cost, stay duration, and number of travelers.

    Args:
        destination_id: Unique string identifier of the destination (e.g. 'tokyo', 'paris', 'kyoto').
        days: Number of days for the trip.
        travelers: Number of travelers (default is 1).

    Returns:
        A dictionary with budget breakdown including daily cost and total estimated cost.
    """
    dest = get_destination_details(destination_id)
    if "error" in dest:
        return dest

    daily_cost = float(dest.get("average_cost_per_day", 150.0))
    total_cost = daily_cost * days * travelers
    return {
        "destination_id": dest["id"],
        "destination_name": dest.get("name", destination_id),
        "days": days,
        "travelers": travelers,
        "average_cost_per_day_usd": daily_cost,
        "total_estimated_cost_usd": round(total_cost, 2),
    }


def get_exchange_rates(base_currency: str = "USD") -> dict:
    """Fetches live currency exchange rates from ExchangeRate-API (open.er-api.com).

    Args:
        base_currency: 3-letter currency code (e.g., 'USD', 'EUR', 'GBP', 'JPY'). Default is 'USD'.

    Returns:
        A dictionary containing base currency, update time, and live exchange rates for major currencies.
    """
    import json
    import os
    import urllib.request

    api_key = os.environ.get("EXCHANGE_RATE_API_KEY", "")
    base = base_currency.upper().strip()
    url = f"https://open.er-api.com/v6/latest/{base}"

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "TravelConciergeAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            rates = data.get("rates", {})
            target_currencies = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY"]
            filtered_rates = {c: rates[c] for c in target_currencies if c in rates}
            return {
                "base_currency": base,
                "update_time_utc": data.get("time_last_update_utc"),
                "rates": filtered_rates,
            }
    except Exception as e:
        return {"error": f"Failed to fetch exchange rates: {str(e)}"}


def geocode_address(address: str) -> dict:
    """Converts a street address or landmark into geographic coordinates using Google Maps Geocoding API.

    Args:
        address: Address or landmark name (e.g. 'Shibuya Crossing, Tokyo' or 'Eiffel Tower, Paris').

    Returns:
        A dictionary containing formatted address, latitude, longitude, and place ID.
    """
    import json
    import os
    import urllib.parse
    import urllib.request

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable not set."}

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "TravelConciergeAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "OK" and data.get("results"):
                res = data["results"][0]
                loc = res["geometry"]["location"]
                return {
                    "query_address": address,
                    "formatted_address": res.get("formatted_address"),
                    "location": {"latitude": loc["lat"], "longitude": loc["lng"]},
                    "place_id": res.get("place_id"),
                }
            return {
                "error": data.get("error_message")
                or f"Geocoding failed with status: {data.get('status')}"
            }
    except Exception as e:
        return {"error": f"Geocoding error: {str(e)}"}


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: float = 1000.0,
) -> list:
    """Finds nearby places of a given type near coordinates using Google Places API (New).

    Args:
        latitude: Latitude of the center point (e.g. 35.6595).
        longitude: Longitude of the center point (e.g. 139.7005).
        place_type: Place type to search for (e.g. 'restaurant', 'tourist_attraction', 'museum', 'cafe', 'hotel'). Default is 'restaurant'.
        radius_meters: Search radius in meters (default 1000.0).

    Returns:
        A list of nearby place dictionaries containing name, address, location, and rating.
    """
    import json
    import os
    import urllib.request

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable not set."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.types",
    }
    body = json.dumps({
        "includedTypes": [place_type.lower().strip()],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            places = data.get("places", [])
            results = []
            for p in places:
                results.append({
                    "name": p.get("displayName", {}).get("text", "Unknown"),
                    "address": p.get("formattedAddress", "N/A"),
                    "location": p.get("location", {}),
                    "rating": p.get("rating"),
                    "types": p.get("types", []),
                })
            return results
    except Exception as e:
        return [{"error": f"Places API error: {str(e)}"}]


async def generate_destination_image(
    prompt: str,
    filename: str = "destination_image.jpeg",
    tool_context: ToolContext = None,
) -> str:
    """Generates an image for a travel destination or landmark using gemini-3.1-flash-lite-image model in global region.

    Saves the generated image as a session artifact for the Playground and uploads the image bytes directly to Cloud Storage.

    Args:
        prompt: Visual description of the image to generate (e.g. 'A stunning sunset over Mount Fuji with cherry blossoms').
        filename: Optional filename for the saved artifact (default 'destination_image.jpeg').
        tool_context: ToolContext injected by ADK to save session artifacts.

    Returns:
        The public HTTPS URL of the uploaded image in Cloud Storage.
    """
    import uuid
    from google import genai
    from google.cloud import storage
    from google.genai import types

    # 1. Generate image using gemini-3.1-flash-lite-image in global region
    genai_client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )

    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    image_bytes = None
    mime_type = "image/jpeg"
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            mime_type = part.inline_data.mime_type or "image/jpeg"
            break

    if not image_bytes:
        return "Error: No image content generated."

    # (1) Save artifact with tool_context.save_artifact for Playground panel
    if tool_context:
        artifact_part = types.Part.from_bytes(
            data=image_bytes, mime_type=mime_type
        )
        await tool_context.save_artifact(
            filename=filename, artifact=artifact_part
        )

    # (2) Upload image bytes directly to Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

    ext = ".png" if "png" in mime_type else ".jpeg"
    safe_filename = (
        filename if filename.endswith(ext) else f"{filename}{ext}"
    )
    unique_blob_name = f"generated/{uuid.uuid4().hex[:8]}_{safe_filename}"

    blob = bucket.blob(unique_blob_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = (
        f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob.name}"
    )
    return public_url


async def generate_destination_video(
    prompt: str,
    filename: str = "destination_video.mp4",
    tool_context: ToolContext = None,
) -> str:
    """Generates a short video for an item in the travel domain (e.g. a destination preview) using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Args:
        prompt: Visual description of the video to generate (e.g. 'A scenic aerial view of Tokyo Tower at sunset').
        filename: Optional filename for the saved artifact (default 'destination_video.mp4').
        tool_context: ToolContext injected by ADK to save session artifacts.

    Returns:
        The public HTTPS URL of the uploaded video in Cloud Storage.
    """
    import base64
    import uuid
    from google import genai
    from google.cloud import storage
    from google.genai import types

    # 1. Generate video using gemini-omni-flash-preview in global region via Interactions API
    genai_client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )

    response = genai_client.interactions.create(
        model="gemini-omni-flash-preview",
        input=prompt,
        response_format=[{"type": "video"}],
    )

    video_bytes = None
    mime_type = "video/mp4"

    if hasattr(response, "output_video") and response.output_video:
        if getattr(response.output_video, "data", None):
            raw_data = response.output_video.data
            video_bytes = base64.b64decode(raw_data) if isinstance(raw_data, (str, bytes)) else raw_data
        elif getattr(response.output_video, "uri", None):
            uri = response.output_video.uri
            if uri.startswith("gs://"):
                storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
                bucket_name = uri.split("/")[2]
                blob_path = "/".join(uri.split("/")[3:])
                video_bytes = storage_client.bucket(bucket_name).blob(blob_path).download_as_bytes()
            elif uri.startswith("http"):
                import urllib.request
                video_bytes = urllib.request.urlopen(uri).read()

    if not video_bytes:
        return "Error: No video content generated."

    # (1) Save artifact with tool_context.save_artifact for Playground panel
    if tool_context:
        artifact_part = types.Part.from_bytes(
            data=video_bytes, mime_type=mime_type
        )
        await tool_context.save_artifact(
            filename=filename, artifact=artifact_part
        )

    # (2) Upload video bytes directly to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

    ext = ".mp4"
    safe_filename = filename if filename.endswith(ext) else f"{filename}{ext}"
    unique_blob_name = f"videos/{uuid.uuid4().hex[:8]}_{safe_filename}"

    blob = bucket.blob(unique_blob_name)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob.name}"
    return public_url



schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Travel Concierge, a helpful AI travel assistant. You can look up current time, weather, "
        "read/write travel destinations in Firestore, calculate trip budgets, check live exchange rates, "
        "geocode locations, find nearby places, generate destination images and video previews using Gemini, safely execute Python code in a sandbox, "
        "and remember user preferences, facts, and ALL user allergies or dietary restrictions across sessions. "
        "Pay special attention to any food, environmental, or medication allergies mentioned by the user, remember them across conversations, "
        "and strictly account for them when recommending places, restaurants, or trip itineraries."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=a2ui_instruction,
    tools=[
        AutoMemoryPreloadTool(),
        get_weather,
        get_current_time,
        list_destinations,
        get_destination_details,
        add_destination,
        calculate_trip_budget,
        get_exchange_rates,
        geocode_address,
        search_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)




app = App(
    root_agent=root_agent,
    name="app",
)




