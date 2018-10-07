# coding=utf8

"""

 MP3 Voice Stamp

 Athletes' companion: adds synthetized voice overlay with various
 info and on-going timer to your audio files

 Copyright ©2018 Marcin Orlowski <mail [@] MarcinOrlowski.com>

 https://github.com/MarcinOrlowski/Mp3VoiceStamp

"""

from __future__ import print_function

import os
import shutil
import tempfile

from .audio import Audio
from .mp3_file_info import Mp3FileInfo
from .util import Util


class Job(object):

    def __init__(self, config):
        self.__config = config
        self.__tmp_dir = None
        self.__tmp_mp3_file = None

    def get_out_file_name(self, music_track):
        """Build out file name based on provided template and music_track data
        """
        out_base_name, out_base_ext = Util.split_file_name(music_track.file_name)
        formatted_file_name = self.__config.file_out_format.format(name=out_base_name, ext=out_base_ext)

        out_file_name = os.path.basename(music_track.file_name)
        if self.__config.file_out is None:
            out_file_name = os.path.join(os.path.dirname(music_track.file_name), formatted_file_name)
        else:
            if os.path.isfile(self.__config.file_out):
                out_file_name = self.__config.file_out
            else:
                if os.path.isdir(self.__config.file_out):
                    out_file_name = os.path.join(self.__config.file_out, formatted_file_name)

        return out_file_name

    def __make_temp_dir(self):
        import tempfile

        self.__tmp_dir = tempfile.mkdtemp()

    def __cleanup(self):
        if self.__tmp_dir is not None and os.path.isdir(self.__tmp_dir):
            shutil.rmtree(self.__tmp_dir)
            self.__tmp_dir = None

        if self.__tmp_mp3_file is not None and os.path.isfile(self.__tmp_mp3_file):
            os.remove(self.__tmp_mp3_file)

    def speak_to_wav(self, text, out_file_name):
        rc = Util.execute_rc(
            ['espeak', '-s', str(self.__config.speech_speed), '-z', '-w', out_file_name, str(text)])
        return rc == 0

    def __create_voice_wav(self, segments, speech_wav_file_name):
        for idx, segment_text in enumerate(segments):
            segment_file_name = os.path.join(self.__tmp_dir, '{}.wav'.format(idx))
            if not self.speak_to_wav(segment_text, segment_file_name):
                raise RuntimeError('Failed to create "{0}" as "{1}".'.format(segment_text, segment_file_name))

        # we need to get the frequency of speech waveform generated by espeak to later be able to tell
        # ffmpeg how to pad/clip the part
        import wave
        wav = wave.open(os.path.join(self.__tmp_dir, '0.wav'), 'rb')
        speech_frame_rate = wav.getframerate()
        wav.close()

        # merge voice overlay segments into one file with needed padding
        concat_cmd = ['ffmpeg', '-y']
        filter_complex = ''
        filter_complex_concat = ';'
        separator = ''

        max_len_tick = speech_frame_rate * 60 * self.__config.tick_interval
        max_len_title = speech_frame_rate * 60 * self.__config.tick_offset
        for idx, _ in enumerate(segments):
            concat_cmd.extend(['-i', os.path.join(self.__tmp_dir, '{}.wav'.format(idx))])

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
            min_track_length = 1 + self.__config.tick_offset
            if music_track.duration < min_track_length:
                raise ValueError(
                    'Track too short (min. {}, current len {})'.format(min_track_length, music_track.duration))

            # check if we can create output file too
            if not self.__config.dry_run_mode:
                if os.path.exists(self.get_out_file_name(music_track)) and not self.__config.force_overwrite:
                    raise OSError('Target "{}" already exists. Use -f to force overwrite.'.format(
                        self.get_out_file_name(music_track)))

                # create temporary folder
                self.__make_temp_dir()

            # let's now create WAVs with our spoken parts.
            ticks = range(self.__config.tick_offset, music_track.duration, self.__config.tick_interval)
            extras = {'config_name': self.__config.name}

            # First goes track title, then time ticks
            # NOTE: we will generate title WAV even if i.e. title_format is empty. This is intentional, to keep
            #       further logic simpler, because if both title and tick formats would be empty, then skipping
            #       WAV generation would left us with no speech overlay file for processing and mixing.
            #       I do not want to have the checks for such case
            track_title_to_speak = Util.prepare_for_speak(
                Util.process_placeholders(self.__config.title_format,
                                          Util.merge_dicts(music_track.get_placeholders(), extras)))

            segments = [track_title_to_speak]

            if self.__config.tick_format != '':
                for time_marker in ticks:
                    extras = {'minutes': time_marker}
                    tick_string = Util.process_placeholders(self.__config.tick_format,
                                                            Util.merge_dicts(music_track.get_placeholders(), extras))
                    segments.append(Util.prepare_for_speak(tick_string))

            if self.__config.dry_run_mode:
                Util.print('  Duration: {} mins, tick count: {}'.format(music_track.duration, (len(segments) - 1)))
                Util.print('  Voice title: "{}"'.format(track_title_to_speak))

            if not self.__config.dry_run_mode:
                speech_wav_full = os.path.join(self.__tmp_dir, 'speech.wav')

                self.__create_voice_wav(segments, speech_wav_full)

                # convert source music track to WAV
                music_wav_full_path = os.path.join(self.__tmp_dir, os.path.basename(music_track.file_name) + '.wav')
                music_track.to_wav(music_wav_full_path)

                # calculate RMS amplitude of music track as reference to gain voice to match
                rms_amplitude = Audio.calculate_rms_amplitude(music_wav_full_path)

                target_speech_rms_amplitude = rms_amplitude * self.__config.speech_volume_factor
                Audio.adjust_wav_amplitude(music_wav_full_path, target_speech_rms_amplitude)

            # mix all stuff together
            file_out = self.get_out_file_name(music_track)
            if not self.__config.dry_run_mode:
                Util.print_no_lf('Writing: "{}"'.format(file_out))

                # noinspection PyProtectedMember
                self.__tmp_mp3_file = os.path.join(os.path.dirname(file_out),
                                                   next(tempfile._get_candidate_names()) + '.mp3')

                # noinspection PyUnboundLocalVariable
                Audio.mix_wav_tracks(self.__tmp_mp3_file, music_track.get_encoding_quality_for_lame_encoder(),
                                     [music_wav_full_path, speech_wav_full])

                # copy some ID tags to newly create MP3 file
                music_track.write_id3_tags(self.__tmp_mp3_file)

                if os.path.exists(file_out):
                    os.remove(file_out)

                os.rename(self.__tmp_mp3_file, file_out)
                self.__tmp_mp3_file = None

                Util.print('OK')
            else:
                msg = '  Output file: "{}" '.format(file_out)
                if os.path.exists(self.get_out_file_name(music_track)):
                    msg += ' *** TARGET FILE ALREADY EXISTS ***'
                Util.print(msg)
                Util.print()

        except RuntimeError as ex:
            if not self.__config.debug:
                Util.print_error(ex)
            else:
                raise
            result = False

        finally:
            self.__cleanup()

        return result
