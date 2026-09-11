import os
import re
import time
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. CONNECT TO YOUR FIREBASE FIRESTORE DATABASE
# ==========================================
# Make sure your 'firebase-key.json' file is in the same folder as this script.
# (Download it from Firebase Console -> Project Settings -> Service Accounts -> Generate new private key)
KEY_PATH = "firebase-key.json"

if not os.path.exists(KEY_PATH):
    print(f"⚠️ Warning: '{KEY_PATH}' not found!")
    print("Please place your downloaded Firebase Service Account JSON key as 'firebase-key.json' in this directory.")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(KEY_PATH)
        firebase_admin.initialize_app(cred)
        print(" Connected to Firebase successfully!")
    except Exception as e:
        print(f"❌ Could not initialize Firebase: {e}")
        exit(1)

db = firestore.client()


def normalize_title(title):
    """Clean title string for matching and doc ID creation."""
    return re.sub(r'[^a-zA-Z0-9]+', ' ', title).strip().lower()


def make_doc_id(title):
    """Generate safe document ID for Firestore."""
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower()).strip('_')
    return cleaned or "unknown_title"


def to_arenascan_slug(title):
    """
    Converts a manhwa title to ArenaScan's exact slug format:
    1. Removes apostrophes (' and ’) so "Extra's" -> "Extras", "Demon's" -> "Demons"
    2. Replaces spaces & special characters with hyphens '-'
    3. Strips leading and trailing hyphens
    """
    cleaned = re.sub(r"['’]", "", title.lower())
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "manhwa"


def format_chapter_suffix(chapter_num):
    """Format chapter number: 123.0 -> '123', 12.5 -> '12-5'"""
    if chapter_num == int(chapter_num):
        return str(int(chapter_num))
    return str(chapter_num).replace(".", "-")


def build_arenascan_chapter_url(title, chapter_num, series_url=None):
    """
    Generates authentic direct ArenaScan chapter URL.
    Example: https://arenascan.com/the-extras-academy-survival-guide-chapter-123/
    """
    slug = None
    if series_url and "arenascan.com" in series_url:
        m = re.search(r'/manga/([^/]+)/?', series_url)
        if m:
            slug = m.group(1).strip("-")
    if not slug:
        slug = to_arenascan_slug(title)
    
    ch_suffix = format_chapter_suffix(chapter_num)
    return f"https://arenascan.com/{slug}-chapter-{ch_suffix}/"


def clean_arenascan_chapter_url(url, title, chapter_num, series_url=None):
    """
    Validates and repairs chapter URLs so they never 404.
    If the link points to a series overview (/manga/), contains underscores (_),
    has bad apostrophe replacement (-extra-s-), or is empty, generates the exact direct chapter URL.
    """
    if not url or url == '#' or not url.startswith('http'):
        return build_arenascan_chapter_url(title, chapter_num, series_url)
    
    if 'arenascan.com' in url:
        if '_' in url or '/manga/' in url or '-extra-s-' in url:
            return build_arenascan_chapter_url(title, chapter_num, series_url)
            
    return url


def extract_chapter_number(text):
    """
    Extracts floating point chapter number from text.
    Examples: 'Chapter 184' -> 184.0, 'Ch. 4.5' -> 4.5
    """
    matches = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if matches:
        return float(matches[0])
    return 999.0


def run_scraper():
    print("\n Connecting to ArenaScan Feed...")

    # ==========================================
    # 2. LOAD EXISTING WATCHLIST & DISCOVERIES
    # ==========================================
    watchlist_ref = db.collection('watchlist')
    watchlist_docs = watchlist_ref.stream()
    
    # Store watchlist as a dictionary of { normalized_title: (doc_id, doc_data) }
    my_watchlist = {}
    for doc in watchlist_docs:
        data = doc.to_dict()
        title = data.get('title', '')
        my_watchlist[normalize_title(title)] = (doc.id, data)

    print(f" Tracking {len(my_watchlist)} titles in your reading watchlist.")

    # Load existing discoveries so we don't notify twice for the same discovery
    discoveries_ref = db.collection('discoveries')
    existing_discoveries = {doc.id for doc in discoveries_ref.stream()}
    print(f" Found {len(existing_discoveries)} existing discoveries in database.")

    # Headers to look like a standard desktop web browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }

    base_url = "https://arenascan.com"

    # ==========================================
    # 3. SCAN PAGES 1 TO 5
    # ==========================================
    for page in range(1, 6):
        page_url = f"{base_url}/page/{page}/" if page > 1 else f"{base_url}/"
        print(f"\n Scanning ArenaScan Feed - Page {page}: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"⚠️ Page {page} returned HTTP status {response.status_code}")
                continue
        except Exception as e:
            print(f"❌ Failed to fetch page {page}: {e}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')

        # Selector: Matches standard manga/manhwa update cards on WordPress/Madara/MangaStream themes
        items = soup.select('.page-item-detail, .bsx, .utao, .slide-item, .listupd .bs')
        
        # Fallback if standard classes differ
        if not items:
            items = soup.select('article, .manga-item, .post-item')

        print(f"  Found {len(items)} manhwa cards on page {page}.")

        for item in items:
            # 1. Extract Title
            title_el = item.select_one('.post-title a, .tt, h4 a, h3 a, .title a, a[title]')
            if not title_el:
                continue
            
            raw_title = title_el.get_text(strip=True)
            norm_title = normalize_title(raw_title)
            doc_id = make_doc_id(raw_title)

            # 2. Extract Direct Series URL & Chapter Link
            series_link_el = item.select_one('a[href*="/manga/"]') or title_el
            series_url = series_link_el.get('href', '') if series_link_el else ''
            if series_url.startswith('/'):
                series_url = base_url + series_url

            chapter_el = item.select_one('.chapter-item, .epxs, .chapter, .ch-item, .sub-ch, ul li')
            chapter_text = chapter_el.get_text(strip=True) if chapter_el else "Chapter 1"
            
            # Find direct chapter link tag if present
            chapter_link_el = item.select_one('a[href*="-chapter-"], a[href*="/chapter/"], .chapter-item a, .ch-item a, .sub-ch a')
            raw_chapter_url = chapter_link_el.get('href', '') if chapter_link_el else ''
            if raw_chapter_url and raw_chapter_url.startswith('/'):
                raw_chapter_url = base_url + raw_chapter_url

            chapter_num = extract_chapter_number(chapter_text)

            # Clean and ensure valid chapter URL with no 404s (strips apostrophes, hyphens, avoids underscores)
            chapter_url = clean_arenascan_chapter_url(raw_chapter_url, raw_title, chapter_num, series_url)

            # 3. Extract Cover Image
            img_el = item.select_one('img')
            cover_url = ""
            if img_el:
                cover_url = (
                    img_el.get('data-src') or 
                    img_el.get('data-lazy-src') or 
                    img_el.get('src') or 
                    ""
                )

            # ==========================================
            # 4. ROUTE 1: TITLE IS IN YOUR WATCHLIST
            # ==========================================
            if norm_title in my_watchlist:
                w_doc_id, w_data = my_watchlist[norm_title]
                last_known_chapter = float(w_data.get('latest_chapter', 0))
                current_stored_url = w_data.get('latest_chapter_url', '')

                # Auto-heal any broken existing URL with underscores or /manga/ link in Firestore
                if '_' in current_stored_url or '/manga/' in current_stored_url or '-extra-s-' in current_stored_url:
                    repaired_url = clean_arenascan_chapter_url(current_stored_url, raw_title, last_known_chapter, series_url)
                    watchlist_ref.document(w_doc_id).update({'latest_chapter_url': repaired_url})
                    w_data['latest_chapter_url'] = repaired_url
                    print(f"🔧 Repaired chapter URL for '{raw_title}' in Firestore ➜ {repaired_url}")

                # Check if a new chapter released
                if chapter_num > last_known_chapter:
                    print(f"\n🔔 [NEW CHAPTER RELEASED] '{raw_title}'")
                    print(f"   Old: Ch. {last_known_chapter} ➜ NEW: {chapter_text} ({chapter_num})")
                    print(f"   Link: {chapter_url}")

                    # Update Firebase Firestore!
                    watchlist_ref.document(w_doc_id).update({
                        'title': raw_title,
                        'latest_chapter': chapter_num,
                        'latest_chapter_text': chapter_text,
                        'latest_chapter_url': chapter_url,
                        'cover_url': cover_url or w_data.get('cover_url', ''),
                        'has_unread': True,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })

                    # Update local state
                    w_data['latest_chapter'] = chapter_num
                    w_data['latest_chapter_text'] = chapter_text
                    w_data['latest_chapter_url'] = chapter_url

            # ==========================================
            # 5. ROUTE 2: NEW DISCOVERY (<= 10 CHAPTERS)
            # ==========================================
            elif chapter_num <= 10.0:
                if doc_id not in existing_discoveries:
                    print(f"\n✨ [NEW DISCOVERY (<= 10 Ch.)] '{raw_title}'")
                    print(f"   Chapter: {chapter_text}")
                    print(f"   Link: {chapter_url}")

                    # Store in separate 'discoveries' collection in Firebase
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

        # Respectful delay between page requests
        time.sleep(1.0)

    print("\n Finished scanning all pages. Firestore database is up to date!")


if __name__ == '__main__':
    run_scraper()
