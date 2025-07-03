from yt_dlp import YoutubeDL

# Define search query
search_term = "enter snadman"
max_results = 10

# Format: 'scsearchN:<search_term>' where N = number of results
search_url = f"scsearch{max_results}:{search_term}"

# yt-dlp options (suppress download, only extract info)
ydl_opts = {
    'quiet': True,
    'extract_flat': True,  # Don't download, just list
    'force_generic_extractor': False,
}

with YoutubeDL(ydl_opts) as ydl:
    results = ydl.extract_info(search_url, download=False)
    entries = results.get('entries', [])

# Print basic info for each result
for i, entry in enumerate(entries, start=1):
    try:
        print(entry["thumbnails"][4]["url"])
    except:
        print("no-thumb")
    print(f"{i}. {entry.get('title')} by {entry.get('uploader')}; {entry.get('duration')} | {entry.get('url')}")
