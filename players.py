from nicegui import ui


class LipPlayer:
    """
    Search YT Video from input
    Display thumb and YT Plyer
    On click, copy YT Url to clipboard
    """

    def __init__(self, anime: bool = False):
        self.yt_stream = None
        self.yt_search = None
        self.yt_anime = anime
        self.videos_search = None
        self.limit = 5
        ui.separator()
        with ui.row():
            self.folder = ui.icon('folder', size='md', color='yellow')
            self.folder.style(add='cursor: pointer')
            self.folder.style(add='margin:10px')
            # made necessary checks
            self.folder.on('click', lambda: pick_file_to_analyze())
            # Add an input field for the audio file name
            self.audio_input = ui.input(placeholder='Audio file to analyse', label='Audio File Name')
            self.audio_input.on('focusout', lambda: check_audio_input(audio_input.value))

            self.audio_file = ui.input('YT search')
            self.search_button = ui.button('search', icon='restore_page', color='blue') \
                .tooltip('Click to Validate')
            self.search_button.on_click(lambda: self.search_youtube())
            self.next_button = ui.button('More', on_click=lambda: self.next_search())
            self.next_button.set_visibility(False)
            self.number_found = ui.label('Result : ')

        self.player_display = ui.card()
        with self.player_display:
            ui.label('Search could take some time ....').classes('animate-pulse')

        self.yt_player = ui.page_sticky()


    async def search_youtube(self):
        """ Run Search YT from input """

        def run_search():
            create_task(self.py_search(self.audio_file.value))

        self.search_button.props('loading')
        self.player_display.clear()
        ui.timer(.5, run_search, once=True)

    async def py_search(self, data):
        """ Search for YT from input """

        self.videos_search = VideosSearch(data, limit=self.limit)
        self.yt_search = await self.videos_search.next()

        # number found
        number = len(self.yt_search['result'])
        self.number_found.text = f'Number found: {number}'
        # activate 'more' button
        if number > 0:
            self.next_button.set_visibility(True)
            # re create  result page
            await self.create_yt_page(self.yt_search)
        else:
            self.number_found.text = 'Nothing Found'

        self.search_button.props(remove='loading')

    async def create_yt_page(self, data):
        """ Create YT search result """

        # clear as we recreate
        self.player_display.clear()
        # create
        with self.player_display.classes('w-full self-center'):
            for self.yt_stream in data['result']:
                ui.separator()
                ui.label(self.yt_stream['title'])
                with ui.row(wrap=False).classes('w-1/2'):
                    yt_image = ui.image(self.yt_stream['thumbnails'][0]['url']).classes('self-center w-1/2')
                    yt_image.on('mouseenter', lambda yt_str=self.yt_stream: self.youtube_player(yt_str['id']))
                    with ui.column():
                        ui.label(f'Length: {self.yt_stream["duration"]}')
                        yt_url = ui.label(self.yt_stream['link'])
                        yt_url.tooltip('Click to copy')
                        yt_url.style('text-decoration: underline; cursor: pointer;')
                        yt_url.on('click', lambda my_yt=yt_url: (ui.clipboard.write(my_yt.text),
                                                                 ui.notify('YT Url copied')))
                        with ui.row():
                            yt_watch_close = ui.icon('videocam_off', size='sm')
                            yt_watch_close.tooltip('Player OFF')
                            yt_watch_close.style('cursor: pointer')
                            yt_watch_close.on('click', lambda: self.yt_player.clear())
                            yt_watch = ui.icon('smart_display', size='sm')
                            yt_watch.tooltip('Player On')
                            yt_watch.style('cursor: pointer')
                            yt_watch.on('click', lambda yt_str=self.yt_stream: self.youtube_player(yt_str['id']))


async def player_areas():
    """
    display search result from pytube
    """
    anime = False
    if str2bool(custom_config['animate-ui']):
        animated_player_area = Animate(ui.scroll_area, animation_name_in="backInDown", duration=1.5)
        player_area = animated_player_area.create_element()
        anime = True
    else:
        player_area = ui.scroll_area()

    player_area.bind_visibility_from(CastAPI.player)
    player_area.classes('w-full border')
    CastAPI.search_areas.append(player_area)
    with player_area:
        LipPlayer(anime)



async def player_clear_areas():
    """
    Clear search results
    """

    for area in CastAPI.search_areas:
        try:
            if str2bool(custom_config['animate-ui']):
                animated_area = Animate(area, animation_name_out="backOutUp", duration=1)
                animated_area.delete_element(area)
            else:
                area.delete()
        except Exception as y_error:
            logger.error(traceback.format_exc())
            logger.error(f'Search area does not exist: {y_error}')
    CastAPI.search_areas = []


