IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.heic', '.png', '.bmp', '.tiff', '.tif', '.webp']
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv']

ALL_EXTENSIONS = {ext.lower() for ext in IMAGE_EXTENSIONS + VIDEO_EXTENSIONS}
