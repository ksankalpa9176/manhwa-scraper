// =========================================================================
// 🛠️ CONFIGURATION STEP: PASTE YOUR CONSOLE APP WEB KEYS CONFIG BLOCK HERE!
// =========================================================================
const firebaseConfig = {
  apiKey: "AIzaSyAcEHMf7R8caqyzcmtpyduAFUUW90HHzTQ",
  authDomain: "manhwa-tracker-be510.firebaseapp.com",
  projectId: "manhwa-tracker-be510",
  storageBucket: "manhwa-tracker-be510.firebasestorage.app",
  messagingSenderId: "762652201419",
  appId: "1:762652201419:web:de50bef07b09fa1d43a64e",
  measurementId: "G-3YGH9RWWV8"
};

// Initialize Firebase App instance
firebase.initializeApp(firebaseConfig);
const firestoreDb = firebase.firestore();

// Global tracking variables to store user tracking queries
let activeWatchlistSet = new Set();

// === ACTION 1: ADD INPUT TITLES TO FIREBASE WATCHLIST ===
async function saveWatchlistEntry() {
    const inputField = document.getElementById('manhwaTitleField');
    const titleValue = inputField.value.trim();
    
    if (titleValue) {
        try {
            await firestoreDb.collection('watchlist').add({
                title: titleValue,
                timestamp: firebase.firestore.FieldValue.serverTimestamp()
            });
            inputField.value = '';
            alert('Success! Title added to your tracking targets.');
        } catch (error) {
            console.error("Error adding document to watchlist: ", error);
            alert('Firebase Write Error! Check console log tabs.');
        }
    }
}

// === ACTION 2: REAL-TIME CLOUD CONNECTION MECHANICS ===

// Listen to changes in the 'watchlist' collection
firestoreDb.collection('watchlist').onSnapshot((watchlistSnapshot) => {
    activeWatchlistSet.clear();
    watchlistSnapshot.forEach((doc) => {
        const data = doc.data();
        if (data.title) {
            // Clean up the text parsing to prevent runtime background interface lockups
            activeWatchlistSet.add(data.title.toLowerCase().trim());
        }
    });
    // Triggers full layout sync whenever target items change
    syncManhwaFeeds();
}, (error) => {
    console.error("Watchlist network stream error: ", error);
});

// Primary mapping function rendering items matching your Python scraper setup
function syncManhwaFeeds() {
    firestoreDb.collection('manhwa')
        .orderBy('discovered_at', 'desc')
        .onSnapshot((querySnapshot) => {
            const watchlistContainer = document.getElementById('watchlistFeedPanel');
            const discoveryContainer = document.getElementById('discoveryFeedPanel');
            
            watchlistContainer.innerHTML = '';
            discoveryContainer.innerHTML = '';

            let watchlistCount = 0;
            let discoveryCount = 0;

            querySnapshot.forEach((doc) => {
                const manhwaData = doc.data();
                const rawTitle = manhwaData.title || '';
                const cleanTitle = rawTitle.toLowerCase().trim();
                const chapterNum = manhwaData.last_scanned_chapter || 0;

                // Build card row element wrapper
                const cardItem = document.createElement('div');
                cardItem.className = 'manhwa-row-card';
                cardItem.innerHTML = `
                    <div class="card-meta">
                        <span class="manga-name">${rawTitle}</span>
                        <span class="manga-chapter-badge">Chapter ${chapterNum}</span>
                    </div>
                    <span class="ios-arrow">➔</span>
                `;

                // Handle external navigation routing on item click events
                cardItem.onclick = () => {
                    const searchUrl = `https://arenascan.com{encodeURIComponent(rawTitle)}`;
                    window.open(searchUrl, '_blank');
                };

                // MATCH 1: If item is tracked on your watchlist, place it in 'My Feed'
                if (activeWatchlistSet.has(cleanTitle)) {
                    watchlistContainer.appendChild(cardItem);
                    watchlistCount++;
                } 
                
                // MATCH 2: Discovery layer filter condition rule (under 10 chapters)
                if (chapterNum <= 10) {
                    const discoveryCard = cardItem.cloneNode(true);
                    discoveryCard.onclick = cardItem.onclick; // Secure link bindings mapping
                    discoveryContainer.appendChild(discoveryCard);
                    discoveryCount++;
                }
            });

            // Empty state handlers formatting rules panels
            if (watchlistCount === 0) {
                watchlistContainer.innerHTML = '<div style="color:rgba(255,255,255,0.2); text-align:center; padding: 20px; font-size:14px;">No unread updates on tracked books.</div>';
            }
            if (discoveryCount === 0) {
                discoveryContainer.innerHTML = '<div style="color:rgba(255,255,255,0.2); text-align:center; padding: 20px; font-size:14px;">No recently launched updates found.</div>';
            }
        }, (error) => {
            console.error("Manhwa core tracking nodes collection stream fault: ", error);
        });
}
