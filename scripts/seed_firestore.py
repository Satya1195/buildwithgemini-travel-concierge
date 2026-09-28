# Copyright 2026 Google LLC
# Seed script for Firestore collection 'destinations'

import subprocess
import google.auth
from google.oauth2.credentials import Credentials
from google.cloud import firestore

# CRITICAL: Hardcode the GCP Project ID as a string, not from env var or auth default
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-7ce6bb053187"

SAMPLE_DESTINATIONS = [
    {
        "id": "tokyo",
        "name": "Tokyo",
        "country": "Japan",
        "category": "Culture & Technology",
        "description": "A bustling metropolis blending ultra-modern skyscrapers with historic temples and world-class street food.",
        "rating": 4.9,
        "average_cost_per_day": 180,
        "tags": ["temples", "food", "technology", "shopping"]
    },
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "category": "Romance & Art",
        "description": "The City of Light, famed for its iconic Eiffel Tower, world-class museums like the Louvre, and charming cafes.",
        "rating": 4.8,
        "average_cost_per_day": 210,
        "tags": ["art", "museums", "romance", "bakery"]
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Nature & Tradition",
        "description": "Japan's ancient capital, filled with thousands of classical Buddhist temples, gardens, imperial palaces, and wooden houses.",
        "rating": 4.9,
        "average_cost_per_day": 150,
        "tags": ["nature", "temples", "history", "gardens"]
    },
    {
        "id": "new-york",
        "name": "New York City",
        "country": "USA",
        "category": "City & Entertainment",
        "description": "The Big Apple featuring Broadway theater, Central Park, world-renowned dining, and vibrant neighborhood diversity.",
        "rating": 4.7,
        "average_cost_per_day": 250,
        "tags": ["broadway", "skyscrapers", "museums", "nightlife"]
    },
    {
        "id": "barcelona",
        "name": "Barcelona",
        "country": "Spain",
        "category": "Architecture & Coast",
        "description": "Famed for Antoni Gaudi's whimsical architecture, sandy Mediterranean beaches, and lively tapas bars.",
        "rating": 4.8,
        "average_cost_per_day": 160,
        "tags": ["architecture", "beaches", "tapas", "sun"]
    }
]

def get_firestore_client():
    try:
        # First try default client
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        # Test read access
        list(db.collection("destinations").limit(1).stream())
        return db
    except Exception:
        # Fallback to gcloud access token if default creds lack local permissions
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
        creds = Credentials(token)
        return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=creds)

def seed():
    print(f"Connecting to Firestore (project: {FIRESTORE_PROJECT_ID})...")
    db = get_firestore_client()
    collection_ref = db.collection("destinations")
    
    for item in SAMPLE_DESTINATIONS:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"Seeded destination: {item['name']} ({doc_id})")
        
    print("Firestore seeding completed successfully!")

if __name__ == "__main__":
    seed()
