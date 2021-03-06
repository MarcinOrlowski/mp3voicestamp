
![MP3 Voice Stamp Logo](img/banner.png)

## Usage ##

 * [Examples](#examples)
 * [Dry-run mode](#dry-run-mode)
 * [Configuration files](#configuration-files)
 * [Formatting spoken messages](#formatting-spoken-messages)


## Examples ##

 The simplest use case is like this:

    mp3voicestamp -i music.mp3

 which would produce file named `music (mp3voicestamp).mp3` with audio overlay added to it with track title
 and time stamps every 5 minute. You can also provide own name for result file using `--out`:
 
    mp3voicestamp -i music.mp3 -o music_with_voice.mp3

 You can also process more than one file at once:
 
    mp3voicestamp -i file1.mp3 file2.mp3 file3.mp3

 When using multiple input files you can still use `--out` but in such case it must point to target folder
 (so you loose ability to manually specify target file name):
 
    mp3voicestamp -i file1.mp3 file2.mp3 file3.mp3 -o my_folder

 You can change certain parameters, incl. frequency of tick announcer, or i.e. boost (or decrease) volume of voice
 overlay (relative to auto calculated volume level), change template for spoken track title or time announcements. 
  
 Sample MP3 include with project was created with:
 
    mp3voicestamp --in music.mp3 --tick-offset 1 --tick-interval 1 --speech-volume 2

 or in short notation
 
     mp3voicestamp -i music.mp3 -to 1 -ti 1 -sv 2
 
 See all available options with `--help` (or `-h`).

## Dry-run mode ##

 For testing purposes, there's dry-run mode available as well, which is extremely useful with batch processing.
 By adding `--dry-run` to your command line arguments, you make the app process all the files, but instead
 of speaking, normalizing, mixing etc, it will just simulate this and print all the info you may be interested
 seeing as what will be the spoken title or how many ticks will be added to each file:
 
    mp3voicestamp -i *.mp3 --dry-run

 would produce no result files, but the following output only:
    
    Files to process: 2
    Title format: "{title}"
    Tick format: "{minutes} minutes"
    Ticks interval 5 mins, start offset: 5 mins

    Processing "Momentum 49.mp3"
      Duration: 143 mins, tick count: 28
      Voice title: "Momentum 49"
      Output file "Momentum 49 (mp3voicestamp).mp3" *** FILE ALREADY EXISTS ***

    Processing "Clay van Dijk guest mix.mp3"
      Duration: 61 mins, tick count: 12
      Voice title: "Clay van Dijk guest mix"
      Output file "Clay van Dijk guest mix (mp3voicestamp).mp3" 
 

## Configuration files ##

 `Mp3VoiceStamp` supports configuration files, so you can easily create one with settings of your choice and
 then use your file instead of passing all custom values via command line switches. It can also save current
 configuration to a file so you can easily preserve your settings with no hassle.
 
 Configuration file is plain text file following [INI file format](https://en.wikipedia.org/wiki/INI_file):
 
    [mp3voicestamp]
    file_out_format = "{name} (mp3voicestamp).{ext}"

    speech_speed = 150
    speech_volume_factor = 1.0

    title_format = "{title}"

    tick_add = 0
    tick_format = "{minutes} minutes"
    tick_offset = 5
    tick_interval = 5

 All keys are optional, so you can put just these you want to be custom. All other values will then fall back
 to defaults:

    [mp3voicestamp]
    tick_format = "{minutes} long minutes passed"

 To use config file specify path to the file with `--config` (or `-c`):
 
    mp3voicestamp -i music.mp3 -c my-settings.ini

 Additionally, command line arguments overshadow config file parameters. For example if you save the following 
 config file as your `config.ini`:
 
    [mp3voicestamp]
    tick_format = "{minutes} minutes"
    tick_offset = 5
    tick_interval = 5

 and then invoke tool like this:
 
    mp3voicestamp -i music.mp3 -c config.ini --tick-offset 10

 then `tick offset` will be set to `10`, shadowing config file entry.
 
 Finally `[mp3voicestamp]` is a section header and must always be present in the file. You also add comments
 with use of `#` at beginning of comment line. See [example config file](../config/example.ini).
 
 ### Saving configuration files ###
 
 You can use `--config-save` (`-cs`) option to dump current configuration state to a file for further reuse:
 
    mp3voicestamp -cs new-config.ini
 
 More over you can combine saving with config loading and manual tweaks as well:
 
    mp3voicestamp -c old-config.ini --tick-offset 10 --tick-format "{minutes} passed" -cs new-config.ini

 Which would load `old-config.ini` file, apply `tick-offset` and `tick-template` from your command line arguments
 and save it all to `new-config.ini` file which you can then reuse as usual using said `--config` option.
 
## Formatting spoken messages ##

 You can define how both track title and clock tickets should be spoken by using configuring the format, 
 using supported placeholders. Each placeholder uses `{name}` format and is then substituted by either
 the correct value, or if no value can be obtained (i.e. MP3 tags are not available) by empty string.
 You can combine multiple placeholders as well as enter regular text.
 
 ### Track title ###

 Default track title format string is `{title} {config_name}`. 
 
 | Key            | Description                                                                      |
 | -------------- | -------------------------------------------------------------------------------- |
 | {title}        | Track title from MP3 tags or based on file name if no tag is set                 |
 | {track_number} | Track number as set in tags or empty string                                      |
 | {artist}       | Artist name (if set) or album artist, otherwise empty string                     |
 | {album_artist} | Album artist or empty string                                                     |
 | {album_title}  | Album title or empty string                                                      |
 | {composer}     | Track composer or empty string                                                   |
 | {comment}      | Content of track comment field or empty string                                   |
 | {config_name}  | Name of loaded config file as specified with `config_name` key or empty string   |
 | {file_name}    | Name of the audio file without name extension                                    |

 > ![Tip](img/tip-small.png) If you don't want to have track title announced, set title format to empty 
 > string either in config or via command line argument `--title-format ""` 
 
 ### Ticks ###

 Default tick title format string is `{minutes} minutes`.

 | Key              | Description                                                                   |
 | ---------------- | ----------------------------------------------------------------------------- |
 | {minutes}        | Minutes since start of the track                                              | 
 | {minutes_digits} | Minutes but spoken as separate digits (i.e. "32" will be said as "three two") | 
 
 If you want, you can also use any of the track title placeholders in tick format too!
 
 > ![Tip](img/tip-small.png) If you don't want to have ticks said, tick format to empty 
 > string either in config or via command line argument `--tick-format ""`.
 