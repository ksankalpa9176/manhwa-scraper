import os
import re
import time
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 1. CONNECT TO YOUR FIREBASE DATABASE
KEY_FILE = "firebase-key.json"

if not os.path.exists(KEY_FILE):
    print(f"⚠️ Warning: '{KEY_FILE}' not found! Place your service account key here.")

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred)

db = firestore.client()


def normalize_title(title):
    return re.sub(r'[^a-zA-Z0-9]+', ' ', title).strip().lower()


def make_doc_id(title):
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower()).strip('_')
    return cleaned or "unknown_title"


def extract_chapter_number(text):
    matches = re.findall(r"[-+]?\d*\.?\d+", text)
    if matches:
        return float(matches[0])
    return 999.0


def run_scraper():
    print("🚀 Connecting to ArenaScan Feed...")

    # Load your reading list
    watchlist_ref = db.collection('watchlist')
    my_watchlist = {
        normalize_title(doc.to_dict().get('title', '')): (doc.id, doc.to_dict())
        for doc in watchlist_ref.stream()
    }
    print(f"📋 Tracking {len(my_watchlist)} titles in your reading list.")

    # Load existing discoveries so we notify only once
    discoveries_ref = db.collection('discoveries')
    existing_discoveries = {doc.id for doc in discoveries_ref.stream()}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    base_url = "https://arenascan.com"

    # Scan Pages 1 to 5
    for page in range(1, 6):
        page_url = f"{base_url}/page/{page}/" if page > 1 else f"{base_url}/"
        print(f"🔍 Scanning ArenaScan Page {page}...")

        try:
            res = requests.get(page_url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            continue

        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('.page-item-detail, .bsx, .utao, .slide-item, .listupd .bs, article')

        for item in items:
            title_el = item.select_one('.post-title a, .tt, h4 a, h3 a, .title a')
            if not title_el:
                continue

            raw_title = title_el.get_text(strip=True)
            norm_title = normalize_title(raw_title)
            doc_id = make_doc_id(raw_title)

            chapter_el = item.select_one('.chapter-item a, .epxs, .chapter, .ch-item a')
            chapter_text = chapter_el.get_text(strip=True) if chapter_el else "Chapter 1"
            chapter_url = chapter_el.get('href', '') if chapter_el else title_el.get('href', '')
            if chapter_url.startswith('/'):
                chapter_url = base_url + chapter_url

            chapter_num = extract_chapter_number(chapter_text)

            img_el = item.select_one('img')
            cover_url = ""
            if img_el:
                cover_url = img_el.get('data-src') or img_el.get('data-lazy-src') or img_el.get('src') or ""

            # 1. Title is in your reading list
            if norm_title in my_watchlist:
                w_doc_id, w_data = my_watchlist[norm_title]
                last_known = float(w_data.get('latest_chapter', 0))

                if chapter_num > last_known:
                    print(f"🔔 [NEW CHAPTER] {raw_title}: {chapter_text}")
                    watchlist_ref.document(w_doc_id).update({
                        'title': raw_title,
                        'latest_chapter': chapter_num,
                        'latest_chapter_text': chapter_text,
                        'latest_chapter_url': chapter_url,
                        'cover_url': cover_url or w_data.get('cover_url', ''),
                        'has_unread': True,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                    w_data['latest_chapter'] = chapter_num

            # 2. New discovery with <= 10 chapters
            elif chapter_num <= 10.0:
                if doc_id not in existing_discoveries:
                    print(f"✨ [NEW DISCOVERY (<= 10 Ch.)] {raw_title} - {chapter_text}")
                    discoveries_ref.document(doc_id).set({
                        'title': raw_title,
                        'latest_chapter': chapter_num,
                        'latest_chapter_text': chapter_text,
                        'latest_chapter_url': chapter_url,
                        'cover_url': cover_url,
                        'notified': True,
                        'created_at': firestore.SERVER_TIMESTAMP
                    })
                    existing_discoveries.add(doc_id)

        time.sleep(1.0)

    print("✅ Finished! Your Firebase database and GitHub Pages are up to date.")


if __name__ == '__main__':
    run_scraper()
