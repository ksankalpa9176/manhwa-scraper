import os
import re
import time
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 1. CONNECT TO YOUR FIREBASE DATABASE
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()


def extract_chapter_number(text):
    """Turns chapter text like 'Chapter 9' or 'Ch. 4.5' into a floating number."""
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if numbers:
        return float(numbers[0])
    return 999.0


def run_scraper():
    print("🚀 Connecting to Arenascan Feed...")

    # 2. LOAD YOUR WATCHLIST FROM FIREBASE
    watchlist_docs = db.collection('watchlist').stream()
    my_watchlist = {doc.to_dict().get('title', '').lower().strip() for doc in watchlist_docs}
    print(f"Tracking {len(my_watchlist)} titles from your watchlist.")

    # 3. AUTOMATED PAGINATION LOOP (Pages 1 to 5)
    for page in range(1, 6):
        print(f"Scanning Arenascan Page {page}...")

        # 🛠️ ERROR-PROOF FIX: Hardcode paths separately so Python never creates 'arenascan.compage'
        if page == 1:
            url = "https://arenascan.com/"
        else:
            url = f"https://arenascan.com/page/{page}/"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            # setting verify=True forces full strict SSL parsing, solving structural host drops
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                print(f"⚠️ Page {page} inaccessible (Status Code: {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Arenascan structural layout containers
            manga_items = soup.find_all('div', class_='utao') or soup.find_all('div', class_='bsx')

            for item in manga_items:
                title_element = item.find('h4') or item.find('div', class_='tt')

                # Extract the direct link to the item
                link_element = item.find('a')
                manhwa_url = link_element['href'] if link_element and link_element.has_attr('href') else url

                chapter_element = item.find('ul').find('li') if item.find('ul') else None
                if not title_element:
                    continue

                title = title_element.text.strip()
                title_lower = title.lower()

                chapter_text = chapter_element.text.strip() if chapter_element else "Chapter 0"
                current_chapter = extract_chapter_number(chapter_text)

                # Safe document ID for Firestore
                doc_id = re.sub(r'[^a-z0-9]', '_', title_lower)

                # Check if this manhwa already exists in database
                manhwa_ref = db.collection('manhwa').document(doc_id)
                manhwa_doc = manhwa_ref.get()

                if not manhwa_doc.exists:
                    # 🚨 NEW MANHWA DISCOVERED
                    print(f"\n✨ NEW MANHWA DISCOVERED: {title} ({chapter_text})")
                    print(f"🔗 Read Here: {manhwa_url}")
                    print("👉 Showing this once. Add it to your app's watchlist if you want to keep tracking it!\n")

                    manhwa_ref.set({
                        'title': title,
                        'last_scanned_chapter': current_chapter,
                        'discovered_at': firestore.SERVER_TIMESTAMP
                    })

                else:
                    # 🔄 MANHWA ALREADY KNOWN
                    if title_lower in my_watchlist:
                        data = manhwa_doc.to_dict()
                        last_chapter = data.get('last_scanned_chapter', 0.0)

                        if current_chapter > last_chapter:
                            print(f"\n🔥 UPDATE for Watchlist Item [{title}]: {chapter_text} is out!")
                            print(f"🔗 Read Update Here: {manhwa_url}\n")
                            manhwa_ref.update({'last_scanned_chapter': current_chapter})
                    else:
                        continue

        except Exception as e:
            print(f"❌ Error scanning page {page}: {e}")

        time.sleep(2)


if __name__ == "__main__":
    run_scraper()
