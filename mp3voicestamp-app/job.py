# coding=utf8

"""

 MP3 Voice Stamp

 Athletes' companion: add synthetized voice overlay with various
 info and on-going timer to your audio files

 Copyright ©2018 Marcin Orlowski <mail [@] MarcinOrlowski.com>

 https://github.com/MarcinOrlowski/Mp3VoiceStamp

"""

from __future__ import print_function

import os
import shutil

from audio import Audio
from mp3_file_info import Mp3FileInfo
from util import Util


class Job(object):

    def __init__(self, config):
        self.__config = config
        self.__tmp_dir = None

    @property
    def config(self):
        return self.__config

    @property
    def tmp_dir(self):
        return self.__tmp_dir

    def get_out_file_name(self, music_track):
        """Build out file name based on provided template and music_track data
        """
        out_base_name, out_base_ext = os.path.splitext(os.path.basename(music_track.file_name))
        out_base_ext = out_base_ext[1:] if out_base_ext[0:1] == '.' else out_base_ext
        formatted_file_name = self.config.file_out_format.format(name=out_base_name, ext=out_base_ext)

        out_file_name = os.path.basename(music_track.file_name)
        if self.config.file_out is None:
            out_file_name = os.path.join(os.path.dirname(music_track.file_name), formatted_file_name)
        else:
            if os.path.isfile(self.config.file_out):
                out_file_name = self.config.file_out
            else:
                if os.path.isdir(self.config.file_out):
                    out_file_name = os.path.join(self.config.file_out, formatted_file_name)

        return out_file_name

    def __make_temp_dir(self):
        import tempfile

        self.__tmp_dir = tempfile.mkdtemp()

    def __cleanup(self):
        if self.tmp_dir is not None:
            shutil.rmtree(self.tmp_dir)
            self.__tmp_dir = None

    def speak_to_wav(self, text, out_file_name):
        rc = Util.execute_rc(
            ['espeak', '-s', str(self.config.speech_speed), '-z', '-w', out_file_name, str(text)])
        return rc == 0

    def __create_voice_wav(self, segments, speech_wav_file_name):
        for idx, segment_text in enumerate(segments):
            segment_file_name = os.path.join(self.tmp_dir, '{}.wav'.format(idx))
            if not self.speak_to_wav(segment_text, segment_file_name):
                raise RuntimeError('Failed to create "{0}" as "{1}".'.format(segment_text, segment_file_name))

        # we need to get the frequency of speech waveform generated by espeak to later be able to tell
        # ffmpeg how to pad/clip the part
        import wave
        wav = wave.open(os.path.join(self.tmp_dir, '0.wav'), 'rb')
        speech_frame_rate = wav.getframerate()
        wav.close()

        # merge voice overlay segments into one file with needed padding
        concat_cmd = ['ffmpeg', '-y']
        filter_complex = ''
        filter_complex_concat = ';'
        separator = ''

        max_len_tick = speech_frame_rate * 60 * self.config.tick_interval
        max_len_title = speech_frame_rate * 60 * self.config.tick_offset
        for idx, _ in enumerate(segments):
            concat_cmd.extend(['-i', os.path.join(self.tmp_dir, '{}.wav'.format(idx))])

            # samples = rate_per_second * seconds * tick_interval_in_minutes
            max_len = max_len_title if idx == 0 else max_len_tick
            # http://ffmpeg.org/ffmpeg-filters.html#Filtergraph-description
            filter_complex += '{}[{}]apad=whole_len={}[g{}]'.format(separator, idx, max_len, idx)
            separator = ';'

            filter_complex_concat += '[g{}]'.format(idx)

        filter_complex_concat += 'concat=n={}:v=0:a=1'.format(len(segments))

        concat_cmd.extend(['-filter_complex', filter_complex + filter_complex_concat])
        concat_cmd.append(speech_wav_file_name)

        if Util.execute_rc(concat_cmd) != 0:
            raise RuntimeError('Failed to merge voice segments')

    def voice_stamp(self, mp3_file_name):
        result = True

        try:
            Util.print('Processing "{}"'.format(mp3_file_name))

            music_track = Mp3FileInfo(mp3_file_name)

            # some sanity checks first
            min_track_length = 1 + self.config.tick_offset
            if music_track.duration < min_track_length:
                raise ValueError(
                    'Track too short (min. {}, current len {})'.format(min_track_length, music_track.duration))

            # check if we can create output file too
            if os.path.exists(self.get_out_file_name(music_track)) and not self.config.force_overwrite:
                raise OSError('Target "{}" already exists. Use -f to force overwrite.'.format(
                    self.get_out_file_name(music_track)))

            # create temporary folder
            self.__make_temp_dir()

            # let's now create WAVs with our spoken parts.
            # First goes track title, then time ticks
            ticks = range(self.config.tick_offset, music_track.duration, self.config.tick_interval)

            extras = {'config_name': self.config.name}
            segments = [Util.prepare_for_speak(music_track.format_title(self.config.title_format, extras))]

            _ = [segments.append(Util.prepare_for_speak(
                Util.string_format(self.config.tick_format, {'minutes': time_marker}))) for time_marker in ticks]

            speech_wav_full = os.path.join(self.tmp_dir, 'speech.wav')
            self.__create_voice_wav(segments, speech_wav_full)

            # convert source music track to WAV
            music_wav_full_path = os.path.join(self.tmp_dir, os.path.basename(music_track.file_name) + '.wav')
            music_track.to_wav(music_wav_full_path)

            # calculate RMS amplitude of music track as reference to gain voice to match
            rms_amplitude = Audio.calculate_rms_amplitude(music_wav_full_path)

            target_speech_rms_amplitude = rms_amplitude * self.config.speech_volume_factor
            Audio.adjust_wav_amplitude(music_wav_full_path, target_speech_rms_amplitude)

            # mix all stuff together
            file_out = self.get_out_file_name(music_track)
            Util.print_no_lf('Creating "{}" file'.format(file_out))
            Audio.mix_wav_tracks(file_out, music_track.get_encoding_quality_for_lame_encoder(),
                                 [music_wav_full_path, speech_wav_full])
            Util.print('OK')

        except RuntimeError as ex:
            Util.print('*** ' + str(ex))
            result = False

        finally:
            self.__cleanup()

        return result
