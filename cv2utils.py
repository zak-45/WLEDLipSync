"""
# a: zak-45
# d: 23/08/2024
# v: 1.0.0
#
# CV2Utils
#
#          CAST utilities
#
# Image utilities
# cv2 thumb
#
"""

import cv2
import os
import utils
import numpy as np

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
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger.cv2utils')

    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key



class VideoThumbnailExtractor:
    """
    Extract thumbnails from a video or image file.

    thumbnail_width: 160 by default
    get_thumbnails: return a list of numpy arrays (RGB)

    # Usage
    video_path = "path/to/your/video.mp4"
    extractor = VideoThumbnailExtractor(video_path)
    extractor.extract_thumbnails(times_in_seconds=[10, 20, 30])  # Extract thumbnails at specified times

    thumbnail_frames = extractor.get_thumbnails()

    for i, thumbnail_frame in enumerate(thumbnail_frames):
        if thumbnail_frame is not None:
            # Display the thumbnail using OpenCV
            cv2.imshow(f'Thumbnail {i+1}', thumbnail_frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        else:
            print(f"No thumbnail extracted at time {i}.")
    """

    def __init__(self, media_path, thumbnail_width=160):
        self.media_path = media_path
        self.thumbnail_width = thumbnail_width
        self.thumbnail_frames = []

    def is_image_file(self):
        # Check if the file extension is an image format
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        _, ext = os.path.splitext(self.media_path)
        return ext.lower() in image_extensions

    def is_video_file(self):
        # Check if the file can be opened as a video
        cap = cv2.VideoCapture(self.media_path)
        if not cap.isOpened():
            return False
        ret, _ = cap.read()
        cap.release()
        return ret

    async def extract_thumbnails(self, times_in_seconds=None):
        if times_in_seconds is None:
            times_in_seconds = [5]
        if self.is_image_file():
            self.extract_thumbnails_from_image()
        elif self.is_video_file():
            await self.extract_thumbnails_from_video(times_in_seconds)
        else:
            # Provide blank frames if the file is not a valid media file
            self.thumbnail_frames = [self.create_blank_frame() for _ in times_in_seconds]
            logger.warning(f"{self.media_path} is not a valid media file. Generated blank frames.")

    def extract_thumbnails_from_image(self):
        image = cv2.imread(self.media_path)
        if image is not None:
            # Resize the image to the specified thumbnail width while maintaining aspect ratio
            height, width, _ = image.shape
            aspect_ratio = height / width
            new_height = int(self.thumbnail_width * aspect_ratio)
            resized_image = cv2.resize(image, (self.thumbnail_width, new_height))
            self.thumbnail_frames = [resized_image]  # Single thumbnail for images
            logger.debug(f"Thumbnail extracted from image: {self.media_path}")
        else:
            self.thumbnail_frames = [self.create_blank_frame()]
            logger.error("Failed to read image. Generated a blank frame.")

    async def extract_thumbnails_from_video(self, times_in_seconds):
        cap = cv2.VideoCapture(self.media_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video file: {self.media_path}")
            self.thumbnail_frames = [self.create_blank_frame() for _ in times_in_seconds]
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        video_length = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps

        for time_in_seconds in times_in_seconds:
            if time_in_seconds > video_length:
                logger.warning(f"Specified time {time_in_seconds}s is greater than video length {video_length}s. "
                               f"Setting time to {video_length}s.")
                time_in_seconds = video_length

            frame_number = int(time_in_seconds * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            success, frame = cap.read()

            if success:
                # Resize the frame to the specified thumbnail width while maintaining aspect ratio
                height, width, _ = frame.shape
                aspect_ratio = height / width
                new_height = int(self.thumbnail_width * aspect_ratio)
                resized_frame = cv2.resize(frame, (self.thumbnail_width, new_height))

                self.thumbnail_frames.append(resized_frame)
                logger.debug(f"Thumbnail extracted at {time_in_seconds}s.")
            else:
                logger.error("Failed to extract frame.")
                self.thumbnail_frames.append(self.create_blank_frame())

        cap.release()

    def create_blank_frame(self):
        # Create a blank frame with the specified thumbnail width and a default height
        height = int(self.thumbnail_width * 9 / 16)  # Assuming a 16:9 aspect ratio for the blank frame
        blank_frame = np.random.randint(0, 256, (height, self.thumbnail_width, 3), dtype=np.uint8)
        # blank_frame = np.zeros((height, self.thumbnail_width, 3), np.uint8)
        # blank_frame[:] = (255, 255, 255)  # White blank frame
        return blank_frame

    def get_thumbnails(self):
        return [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in self.thumbnail_frames]


