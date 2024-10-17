import musicbrainzngs
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Set the user agent
musicbrainzngs.set_useragent("WLEDLipSync", "0.1", "zak-45@gmail.com")

def get_artist_id(artist_name):
    try:
        result = musicbrainzngs.search_artists(artist=artist_name)
        if result['artist-list']:
            return result['artist-list'][0]['id']
    except musicbrainzngs.WebServiceError as e:
        logging.error(f"Error fetching artist: {e}")
    return None

def get_recording_id(artist_id, recording_name):
    try:
        result = musicbrainzngs.search_recordings(artist=artist_id, recording=recording_name)
        if result['recording-list']:
            return result['recording-list'][0]['id']
    except musicbrainzngs.WebServiceError as e:
        logging.error(f"Error fetching recording: {e}")
    return None

def get_cover_art(recording_id):
    try:
        result = musicbrainzngs.get_release_group_by_id(recording_id, includes=["url-rels"])
        for rel in result['release-group']['url-relation-list']:
            if rel['type'] == 'cover art':
                return rel['target']
    except musicbrainzngs.WebServiceError as e:
        logging.error(f"Error fetching cover art: {e}")
    return None

if __name__ == "__main__":
    artist_name = "Status Quo"
    recording_name = "Roll Over Lay Down"

    artist_id = get_artist_id(artist_name)
    if artist_id:
        recording_id = get_recording_id(artist_id, recording_name)
        if recording_id:
            cover_art_url = get_cover_art(recording_id)
            if cover_art_url:
                print(f"Cover art URL: {cover_art_url}")
            else:
                logging.error(f"No cover art found for recording {recording_name} by {artist_name}")
        else:
            logging.error(f"No recordings found for {recording_name} by {artist_name}")
    else:
        logging.error(f"No artist found with name {artist_name}")
