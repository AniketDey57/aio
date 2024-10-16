import os
import aigpy
import subprocess
import pathlib

from bot.logger import LOGGER
from bot.helpers.tidal.paths import *
from bot.helpers.tidal.tidal import *
from bot.helpers.tidal.decryption import *
from bot.helpers.tidal.settings import TIDAL_SETTINGS

from bot.helpers.metadata import base_metadata, set_metadata
from bot.helpers.utils import get_file_name, handle_upload


def __encrypted__(stream, srcPath, descPath):
    if aigpy.string.isNull(stream.encryptionKey):
        os.replace(srcPath, descPath)
    else:
        key, nonce = decrypt_security_token(stream.encryptionKey)
        decrypt_file(srcPath, descPath, key, nonce)
        os.remove(srcPath)


def __parseContributors__(roleType, Contributors):
    if Contributors is None:
        return None
    try:
        ret = []
        for item in Contributors['items']:
            if item['role'] == roleType:
                ret.append(item['name'])
        return ret
    except:
        return None
    

async def __getMetaData__(track: Track, album: Album, stream, quality):
    #composer = __parseContributors__('Composer', contributors)
    metadata = base_metadata.copy()
    metadata['title'] = track.title
    metadata['album'] = album.title
    metadata['artist'] = TIDAL_API.getArtistsName(track.artists)
    metadata['albumartist'] =  TIDAL_API.getArtistsName(album.artists)
    metadata['tracknumber'] = track.trackNumber
    metadata['date'] = album.releaseDate
    metadata['isrc'] = track.isrc
    if album.numberOfVolumes <= 1:
        metadata['totaltracks'] = album.numberOfTracks
    metadata['volume'] = track.volumeNumber
    metadata['albumart'] = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    metadata['extension'] = getExtension(stream)
    metadata['copyright'] = track.copyRight
    metadata['provider'] = 'tidal'
    metadata['quality'] = "MP3 320K"
    metadata['duration'] = track.duration
    #
    return metadata

# For Posting Cover etc
async def albumMeta(track, album):
    metadata = base_metadata.copy()
    metadata['title'] = album.title
    metadata['album'] = album.title
    metadata['artist'] = TIDAL_API.getArtistsName(track.artists)
    metadata['albumartist'] = TIDAL_API.getArtistsName(track.artists)
    metadata['date'] = album.releaseDate
    metadata['upc'] = album.upc
    if album.numberOfVolumes <= 1:
        metadata['totaltracks'] = album.numberOfTracks
    metadata['volume'] = track.volumeNumber
    metadata['totalvolume'] = album.numberOfVolumes
    metadata['albumart'] = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    metadata['copyright'] = track.copyRight
    metadata['provider'] = 'tidal'
    metadata['quality'] = "MP3 320K"
    metadata['duration'] = album.duration
    metadata['explicit'] = album.explicit
    return metadata

async def downloadTrack(track: Track, album=None, playlist=None, partSize=1048576, \
    user=None, type='track', sid=None):
    try:
        quality = TIDAL_SETTINGS.audioQuality

        stream = TIDAL_API.getStreamUrl(track.id, quality)

        metadata = await __getMetaData__(track, album, stream, quality)
        if sid:
            metadata['item_id'] = sid
        path, _, _ = await get_file_name(user, metadata, type)
        #path = getTrackPath(track, stream, user['r_id'], album, playlist)

        tool = aigpy.download.DownloadTool(path + '.part', [stream.url])
        tool.setPartSize(partSize)
        check, err = tool.start(TIDAL_SETTINGS.showProgress)
        if not check:
            await LOGGER.error(f"DL Track[{track.title}] failed.{str(err)}", user)
            return

        # encrypted -> decrypt and remove encrypted file
        __encrypted__(stream, path + '.part', path)

        # lyrics
        try:
            lyrics = TIDAL_API.getLyrics(track.id).subtitles
        except:
            lyrics = None
        metadata['lyrics'] = lyrics if lyrics else ""

        metadata['thumbnail'] = TIDAL_API.getCoverUrl(album.cover, "80", "80")
        await set_metadata(path, metadata)

        mp3_path = str(path)[:-4] + 'mp3'

        """ffprobe_command = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]

        try:
            original_bitrate = subprocess.check_output(ffprobe_command, stderr=subprocess.STDOUT, universal_newlines=True)
            original_bitrate = original_bitrate.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error getting original bitrate: {e}")
            original_bitrate = '192K'"""

        cmd = f'ffmpeg -i "{path}" -ab 320k -map_metadata 0 -id3v2_version 3 "{mp3_path}"'
        #cmd = f'ffmpeg -i "{path}" -acodec libmp3lame -b:a {original_bitrate} "{mp3_path}" -loglevel panic'
        try:
            with open(os.devnull, 'w') as null_file:
                subprocess.run(cmd, shell=True, check=True, stdout=null_file, stderr=null_file)
        except subprocess.CalledProcessError as e:
            LOGGER.debug(e)
        await handle_upload(user, mp3_path, metadata)

        # Remove the files after uploading
        os.remove(path)

        LOGGER.debug("Succesfully Downloaded " + track.title)
    except Exception as e:
        await LOGGER.error(f"DL Track[{track.title}] failed.{str(e)}", user)

async def downloadTracks(tracks, album: Album = None, playlist : Playlist=None, \
    user=None):
    def __getAlbum__(item: Track):
        album = TIDAL_API.getAlbum(item.album.id)
        return album
    
    for index, item in enumerate(tracks):
        itemAlbum = album
        if itemAlbum is None:
            itemAlbum = __getAlbum__(item)
            item.trackNumberOnPlaylist = index + 1
        await downloadTrack(item, itemAlbum, playlist, user=user, type='album')
