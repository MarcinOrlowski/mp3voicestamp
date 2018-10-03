# coding=utf8

"""

 MP3 Voice Stamp

 Athletes' companion: add synthetized voice overlay with various
 info and on-going timer to your audio files

 Copyright ©2018 Marcin Orlowski <mail [@] MarcinOrlowski.com>

 https://github.com/MarcinOrlowski/mp3voicestamp

"""

from __future__ import print_function

import re
import os
import shutil

from util import Util
from mp3_file_info import Mp3FileInfo


class Job(object):

    def __init__(self, job_config):
        self.job_config = job_config

        self.in_file_info = None
        self.out_file_info = None

        self.tmp_dir = None

    def get_out_file_name(self, music_track):
        """Build out file name based on provided template and music_track data
        """
        out_base_name, out_base_ext = os.path.splitext(os.path.basename(music_track.file_name))
        out_base_ext = out_base_ext[1:] if out_base_ext[0:1] == '.' else out_base_ext
        formatted_file_name = self.job_config.file_out_pattern.format(name=out_base_name, ext=out_base_ext)

        out_file_name = os.path.basename(music_track.file_name)
        if self.job_config.file_out is None:
            out_file_name = os.path.join(os.path.dirname(music_track.file_name), formatted_file_name)
        else:
            if os.path.isfile(self.job_config.file_out):
                out_file_name = self.job_config.file_out
            else:
                if os.path.isdir(self.job_config.file_out):
                    out_file_name = os.path.join(self.job_config.file_out, formatted_file_name)

        return out_file_name

    def make_temp_dir(self):
        import tempfile

        self.tmp_dir = tempfile.mkdtemp()

    def cleanup(self):
        if self.tmp_dir is not None:
            shutil.rmtree(self.tmp_dir)
            self.tmp_dir = None

    def speak_to_wav(self, text, out_file_name):
        rc = Util.execute_rc(
            ['espeak', '-s', str(self.job_config.speech_speed), '-z', '-w', out_file_name, str(text)])
        return rc == 0

    def calculate_rms_amplitude(self, wav_file):
        # now let's get the RMS amplitude of our track
        src_amplitude_cmd = ['sox', wav_file, '-n', 'stat']
        rc, output, err = Util.execute(src_amplitude_cmd)
        if rc != 0:
            raise RuntimeError('Failed to calculate RMS amplitude of "{}"'.format(wav_file))

        # let's check what "sox" figured out
        src_sox_results = {re.sub(' +', '_', err[i].split(':')[0].strip().lower()): err[i].split(':')[1].strip() for i
                           in range(0, len(err))}
        return float(src_sox_results['rms_amplitude'])

    def adjust_wav_amplitude(self, wav_file, rms_amplitude):
        voice_gain_cmd = ['normalize-audio', '-a', str(rms_amplitude), wav_file]
        if Util.execute_rc(voice_gain_cmd) != 0:
            raise RuntimeError('Failed to adjust voice overlay volume')

    def prepare_for_speak(self, text):
        """ Tries to process provided text for more natural sound when spoken, i.e.
            "Track 013" => "Track 13" so no leading zero will be spoken (sorry James...).
            We also replace '-' by coma, to enforce small pause in spoken text
        """
        parts_in = re.sub(' +', ' ', text).replace('-', ',').split(' ')
        parts_out = []
        for part in parts_in:
            match = re.match('[0-9]{2,}', part)
            if match is not None:
                part = str(int(part))
            parts_out.append(part)

        return ' '.join(parts_out)

    def create_voice_wav(self, segments, speech_wav_file_name):
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

        max_len_tick = speech_frame_rate * 60 * self.job_config.tick_interval
        max_len_title = speech_frame_rate * 60 * self.job_config.tick_offset
        for idx, i in enumerate(segments):
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

    def mix_tracks(self, file_out, encoding_quality, music_wav, speech_wav):
        Util.print('Creating "{}" file'.format(file_out))
        merge_cmd = ['ffmpeg', '-y',
                     '-i', os.path.join(self.tmp_dir, music_wav),
                     '-i', speech_wav,
                     '-filter_complex', 'amerge', '-ac', '2', '-c:a', 'libmp3lame',
                     '-q:a', str(encoding_quality),
                     file_out]
        if Util.execute_rc(merge_cmd) != 0:
            raise RuntimeError('Failed to create final MP3 file')

    def voice_stamp(self, mp3_file_name):
        result = True

        try:
            Util.print('Processing "{}"'.format(mp3_file_name))

            music_track = Mp3FileInfo(mp3_file_name)

            # some sanity checks first
            min_track_length = 1 + self.job_config.tick_offset
            assert music_track.duration >= min_track_length, 'Track too short (min. {}, current len {})'.format(
                min_track_length, music_track.duration)

            # check if we can create output file too
            if os.path.exists(self.get_out_file_name(music_track)) and not self.job_config.force_overwrite:
                raise OSError('Target "{}" already exists'.format(self.get_out_file_name(music_track)))

            # create temporary folder
            self.make_temp_dir()

            # let's now create WAVs with our spoken parts.
            # First goes track title, then time stamps
            ticks = range(self.job_config.tick_offset, music_track.duration, self.job_config.tick_interval)

            segments = [self.prepare_for_speak(music_track.format_title(self.job_config.title_pattern))]
            _ = [segments.append(self.prepare_for_speak(self.job_config.tick_pattern.format(time_marker))) for
                 time_marker in ticks]

            speech_wav_full = os.path.join(self.tmp_dir, 'speech.wav')
            self.create_voice_wav(segments, speech_wav_full)

            # convert source music track to WAV
            music_wav_full_path = os.path.join(self.tmp_dir, os.path.basename(music_track.file_name) + '.wav')
            music_track.to_wav(music_wav_full_path)

            # calculate RMS amplitude of music track as reference to gain voice to match
            rms_amplitude = self.calculate_rms_amplitude(music_wav_full_path)

            target_speech_rms_amplitude = rms_amplitude * self.job_config.speech_volume_factor
            self.adjust_wav_amplitude(music_wav_full_path, target_speech_rms_amplitude)

            # mix all stuff together
            print('out ' + self.get_out_file_name(music_track))
            self.mix_tracks(self.get_out_file_name(music_track), music_track.get_encoding_quality_for_lame_encoder(),
                            music_wav_full_path, speech_wav_full)

        except (RuntimeError, AssertionError) as ex:
            Util.print('*** ' + str(ex))
            result = False

        finally:
            self.cleanup()

        return result
