"""
a: zak-45
d: 09/10/2024
v: 1.0.0.0

A class to retrieve music artist information and song lyrics using the YTMusic API.

"""

from ytmusicapi import YTMusic
import os
import utils


class MusicInfoRetriever:
    """
    This class provides methods to search for an artist and retrieve their information,
    as well as to search for a song and obtain its lyrics.

    Attributes:
        yt: An instance of YTMusic to interact with the YTMusic API.

    Methods:
        get_artist_info(artist_name):
            Retrieves information about the specified artist.

        get_song_info_with_lyrics(song_name, artist_name):
            Searches for the specified song by the artist and retrieves its lyrics/info.

    # Example usage
    if __name__ == "__main__":
        retriever = MusicInfoRetriever()
        artist_info = retriever.get_artist_info('century lover')
        print(artist_info)

        info = retriever.get_song_info_with_lyrics('why', 'century lover')
        print(info)
    """

    def __init__(self):
        """
        Initializes an instance of the MusicInfoRetriever class.

        This constructor sets up the YTMusic API client, allowing the instance to
        interact with the YTMusic API for retrieving artist information and song lyrics.
        """
        self.yt = YTMusic()

    def get_artist_info(self, artist_name):
        """
        Retrieves information about the specified artist.

        This method searches for the artist by name and returns their description
        and image URL if found. If no artist is found, it returns None.

        Args:
            artist_name (str): The name of the artist to search for.

        Returns:
            dict or None: A dictionary containing the artist's description and image URL and top5 songs,
                          or None if the artist is not found.
        """

        artists = self.yt.search(artist_name, filter='artists')
        if not artists:
            logger.debug(f"No artists found for '{artist_name}'.")
            return None
        # we take the first record as this is the most probable one
        artist = artists[0]
        artist_id = artist['browseId']
        # grab info
        artist_all_info = self.yt.get_artist(artist_id)

        return {
            'name': artist_all_info['name'],
            'description': artist_all_info['description'],
            'thumbnails': artist_all_info['thumbnails'],
            'id': artist_id,
            'top_5': artist_all_info['songs']['results']
        }

    def search_song(self, artist, song_name, songs_result):
        """
        Searches for a specific song by a given artist within a list of song results.
        This function filters the results to find a match based on the artist's ID and the song name,
        and retrieves detailed information about the song, including its lyrics if available.

        Args:
            artist (dict): A dictionary containing information about the artist, including their ID.
            song_name (str): The name of the song to search for.
            songs_result (list): A list of song dictionaries to search through.

        Returns:
            dict: A dictionary containing details about the found song,
            including title, length, year, lyrics, video ID, album ID, album name, thumbnails, and artist information.
            If no song is found, an empty dictionary is returned.

        """
        song_data = {}
        artist_id = artist['id']
        # iterate over the search result, this could include not expected result (e.g. other artist)
        for index, song in enumerate(songs_result):
            # we take only song from this artist ID
            if song['artists'][0]['id'] == artist_id and song_name.lower() in song['title'].lower():
                # grab video info
                video = self.yt.get_watch_playlist(song['videoId'])
                # put the first result into dict
                if index == 0:
                    song_data = {
                        'title': video['tracks'][0]['title'],
                        'length': video['tracks'][0]['length'],
                        'year': video['tracks'][0]['year'],
                        'lyrics': None,
                        'videoId': video['tracks'][0]['videoId'],
                        'albumId': video['tracks'][0]['album']['id'],
                        'albumName': video['tracks'][0]['album']['name'],
                        'thumbnails': video['tracks'][0]['thumbnail'],
                        'artistInfo': artist
                    }
                # take the first video with lyrics
                if video.get('lyrics') is not None:
                    song_data['lyrics'] = self.yt.get_lyrics(video['lyrics'])
                    break

        return song_data

    def get_song_info_with_lyrics(self, song_name, artist_name):
        """
        Searches for the specified song by the artist and retrieves its lyrics/info.

        This method searches for the song and iterates through the results to find
        the first entry with non-None lyrics. If found, it returns the lyrics; otherwise,
        it returns only info if exist else None.
        Artist info are included.

        Args:
            song_name (str): The name of the song to search for.
            artist_name (str): The name of the artist who performed the song.

        Returns:
            str or None: The lyrics/song info of the song if found, or None if no data are available.

        """
        # search artist to get ID
        artist = self.get_artist_info(artist_name)

        if artist is not None:
            # get all possibility
            songs_possibility = self.yt.search(f"{song_name} {artist_name}", filter='songs')
            # retrieve data for the song
            song_data = self.search_song(artist,song_name,songs_possibility)
            # return only song info if something
            if len(song_data) > 0:
                return song_data

        return None

"""
When this env var exist, this mean run from the one-file compressed executable.
Load of the config is not possible, folder config should not exist.
This avoid FileNotFoundError.
This env not exist when run from the extracted program.
Expected way to work.
"""
if "NUITKA_ONEFILE_PARENT" not in os.environ:
    # read config
    # create logger
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger.utils')

    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key