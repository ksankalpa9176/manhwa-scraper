import os
import re
import time
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 1. CONNECT TO YOUR FIREBASE DATABASE
# Make sure firebase-key.json is placed in the exact same directory as this script!
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()


def extract_chapter_number(text):
    """Turns chapter text like 'Chapter 9' or 'Ch. 4.5' into a floating number (9.0 or 4.5)"""
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if numbers:
        return float(numbers[0])
    return 999.0


def run_scraper():
    print("🚀 Connecting to Arenascan Feed...")

    # 2. LOAD YOUR HAND-TYPED WATCHLIST FROM FIREBASE
    watchlist_docs = db.collection('watchlist').stream()
    my_watchlist = [doc.to_dict().get('title', '').lower().strip() for doc in watchlist_docs]
    print(f"Tracking {len(my_watchlist)} titles from your watchlist.")

    # 3. AUTOMATED PAGINATION LOOP (Pages 1 to 5)
    for page in range(1, 6):
        print(f"Scanning [Arenascan](https://arenascan.com) Page {page}...")

        # ✅ FIX: Properly formatted dynamic slash formatting for layout pages
        if page == 1:
            url = "https://arenascan.com/"
        else:
            url = f"https://arenascan.com/page/{page}/"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                print(f"⚠️ Page {page} inaccessible (Status Code: {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Arenascan structural layout container indicators
            manga_items = soup.find_all('div', class_='utao') or soup.find_all('div', class_='bsx')

            # Fallback tracking backup layout mapping metrics
            if not manga_items:
                manga_items = soup.find_all('div', class_='page-item')

            for item in manga_items:
                # Find the title element inside card structures
                title_element = item.find('h3') or item.find('h4') or item.find('div', class_='tt')

                # Grab all anchor hyper-links bound to target item asset elements
                all_links = item.find_all('a')

                if not title_element or not all_links:
                    continue

                manhwa_title = title_element.text.strip()

                # Filter tracking updates explicitly linking back into chapter logs
                chapter_links = [a for a in all_links if 'chapter' in a.text.lower() or 'ch.' in a.text.lower()]
                if not chapter_links:
                    continue

                # The first layout indexing component yields absolute latest records
                latest_chapter_element = chapter_links[0]
                chapter_text = latest_chapter_element.text.strip()  # e.g., "Chapter 10"
                chapter_url = latest_chapter_element['href']  # e.g., "https://arenascan.com/..."

                clean_title = manhwa_title.lower().strip()
                latest_chapter_num = extract_chapter_number(chapter_text)

                # Process business criteria settings rules mappings
                is_watchlist_match = clean_title in my_watchlist
                is_new_series = latest_chapter_num <= 10.0

                if is_watchlist_match or is_new_series:
                    # Construct structural primary-key tracking layout document IDs
                    doc_id = f"arenascan-{manhwa_title}-{chapter_text}".replace(" ", "-").lower()
                    doc_id = re.sub(r'[^a-z0-9\-]', '', doc_id)

                    doc_ref = db.collection('chapters').document(doc_id)

                    if not doc_ref.get().exists:
                        content_type = 'watchlist' if is_watchlist_match else 'new_series'

                        # Push dynamic record updates live straight into Firestore
                        doc_ref.set({
                            'title': manhwa_title,
                            'chapter': chapter_text,
                            'link': chapter_url,
                            'is_read': False,
                            'type': content_type,
                            'timestamp': firestore.SERVER_TIMESTAMP
                        })
                        print(f"🔥 Success! Uploaded: {manhwa_title} ({chapter_text}) -> [{content_type.upper()}]")

        except Exception as e:
            print(f"❌ Error rendering loop data on page {page}: {e}")

        # Politeness sleep buffer logic
        time.sleep(2)

    print("🏁 Arenascan Pages 1-5 Sync completed.")


if __name__ == "__main__":
    run_scraper()
