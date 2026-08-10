def normalize_artist(title, artists):
    title_low = title.lower()
    for artist in artists:
        if artist.lower() in title_low:
            return True
    return False
