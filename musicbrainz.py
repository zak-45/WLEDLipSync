import musicbrainzngs

# Set the user agent
musicbrainzngs.set_useragent("YourAppName", "0.1", "http://yourappwebsite.com")


def get_artist_info_and_photo(artist_name):
    # Search for the artist
    artist_result = musicbrainzngs.search_artists(artist=artist_name)
    if not artist_result['artist-list']:
        print("Artist not found.")
        return None, None  # Artist not found

    artist = artist_result['artist-list'][0]
    artist_id = artist['id']
    print(f"Found artist: {artist['name']} (ID: {artist_id})")

    # Get detailed artist info
    artist_info = musicbrainzngs.get_artist_by_id(artist_id, includes=['url-rels'])

    # Get artist photo URL if available
    artist_photo = artist_info['artist'].get('life-span', {}).get('begin', None)
    artist_image_url = artist_info['artist'].get('image', None)

    return artist_info['artist'], artist_image_url


# Example usage
artist_name = "The Beatles"
artist_info, artist_photo = get_artist_info_and_photo(artist_name)

if artist_info:
    print(f"Artist Name: {artist_info['name']}")
    print(f"Artist ID: {artist_info['id']}")
    print(f"Artist Photo URL: {artist_photo}" if artist_photo else "No photo available.")
else:
    print("Artist not found.")
