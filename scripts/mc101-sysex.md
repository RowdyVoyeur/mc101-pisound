# Roland MC-101 System Exclusive

This document consolidates the Roland MC-101 System Exclusive knowledge gathered while building the nanokontroller.py script.

It focuses on the address model, data encodings and the offsets currently implemented in the script for live editing. Some notes also capture behaviours discovered during testing, including readable-but-not-live aliases and areas that remain uncertain.

> **Special thanks to [DrKnackerator](https://github.com/DrKnackeratorStrikesAgain/)** for the excellent Roland ZEN research and tools, especially [Roland-Zen-Decode-XML](https://github.com/DrKnackeratorStrikesAgain/Roland-Zen-Decode-XML). The XML decode pages were a key reference point for matching Fantom/ZEN-Core block offsets to the MC-101 address space.

## 1. Executive summary

- Roland DT1 SysEx writes to the MC-101 use manufacturer ID 41, device ID 10 by default, model ID 00 00 00 5E, command 12, four address bytes, one or more 7-bit data bytes, a Roland checksum, and F7.

- The MC-101 uses different base addresses from other Roland instruments, but many parameter offsets match ZEN-Core/Fantom structures such as PCMT_CMN, PCMT_PTL, PCMR_PTL, PTL_LFO, PTL_FENV, PTL_AENV and related blocks.

- Tone editing uses a track base plus a partial stride plus a block/parameter offset. Drum editing uses a drum track base plus a drum-key stride plus a Drum Kit Partial offset.

- The current script contains live SysEx mappings for Drum Kit Partial parameters, Tone Common/Tone Partial parameters, oscillator/filter/envelope/LFO controls, partial switches, structure controls, and a partly verified Matrix Control area.

- Preset 7 Scatter and Preset 8 keyboard/CC mappings use ordinary MIDI note/CC messages, not System Exclusive. They are mentioned only to avoid confusing them with SysEx mappings.

## 2. Roland DT1 SysEx format used by the script

F0 41 10 00 00 00 5E 12 aa bb cc dd data... checksum F7

| **Field**   | **Value / meaning**                 |
|-------------|-------------------------------------|
| F0          | Start of SysEx                      |
| 41          | Roland manufacturer ID              |
| 10          | Device ID used in the script        |
| 00 00 00 5E | MC-101 model ID used in the script  |
| 12          | DT1 data set command                |
| aa bb cc dd | Four 7-bit address bytes            |
| data...     | One or more 7-bit data bytes        |
| checksum    | Roland checksum over address + data |
| F7          | End of SysEx                        |

Checksum formula used by the script:

checksum = (128 - (sum(address_bytes + data_bytes) % 128)) % 128

## 3. Data encodings

| **Script size** | **Encoding**                                                    | **Used for**                                                                 |
|-----------------|-----------------------------------------------------------------|------------------------------------------------------------------------------|
| 1               | One 7-bit byte, 00..7F                                          | Switches, pan, level, source/destination values, many model-specific fields  |
| 2               | Two 7-bit bytes: high 7 bits, low 7 bits                        | 14-bit values when used                                                      |
| 4               | Four Roland nibbles: 0000 aaaa, 0000 bbbb, 0000 cccc, 0000 dddd | 0..1023 and larger values such as wave numbers and many time/rate parameters |
| nibbles2        | Two nibbles: high and low 4-bit values                          | Signed/centred offset-style parameters such as drum offsets and LFO depths   |

Important practical note: many values displayed as negative or centred values are encoded as positive stored values. For example, several 0-centred offsets use a stored range such as 28..228 or 1..127, with 128 or 64 representing displayed zero.

## 4. Address model

### 4.1 Tone track bases

| **Track** | **Base address** |
|-----------|------------------|
| Track 1   | 30.20.00.00      |
| Track 2   | 30.42.00.00      |
| Track 3   | 30.64.00.00      |
| Track 4   | 31.06.00.00      |

Tone partial parameters use the same structure as Level and Pan in Preset 6 Scene 1:

address = tone_track_base[track] + partial_stride[partial] + parameter_offset

partial_stride = (partial - 1) * 00.01.00

| **Example**                                 | **Address** |
|---------------------------------------------|-------------|
| Track 2 Partial 1 Level, offset 00.00.20.00 | 30.42.20.00 |
| Track 2 Partial 1 Pan, offset 00.00.20.07   | 30.42.20.07 |
| Track 2 Partial 2 Level, offset 00.00.20.00 | 30.42.21.00 |
| Track 1 Partial 4 Level, offset 00.00.20.00 | 30.20.23.00 |

### 4.2 Tone track/common and PMT-style parameters

Mappings labelled sysex_track in the script are track-level or tone-common/structure parameters. They use the selected track base, with partial forced to 1 by the handler. Dynamic partial-switch mappings use a per-partial PMT offset such as 00.00.10.02, 00.00.10.0B, 00.00.10.14 or 00.00.10.1D.

track/common address = tone_track_base[track] + offset

partial switch address = tone_track_base[track] + PMT offset for selected partial

### 4.3 Drum track and drum key bases

| **Drum track** | **Base address** |
|----------------|------------------|
| Track 1        | 32.40.00.00      |
| Track 2        | 32.73.00.00      |
| Track 3        | 33.26.00.00      |
| Track 4        | 33.59.00.00      |

Drum Kit Partial parameters are keyed by MIDI note/pitch, not by a simple pad index. The script supports keys 22..108 and also resolves the 16 physical MC-101 pads through the standard pad note list.

drum_key_base = drum_track_base[track] + (00.00.(0x16 + key - 21).00)

drum_parameter_address = drum_key_base + PCMR_PTL_offset

| **Physical pad** | **MIDI pitch/key** | **Track 1 Drum Kit Partial base** |
|------------------|--------------------|-----------------------------------|
| Pad 1            | 37                 | 32.40.26.00                       |
| Pad 2            | 39                 | 32.40.28.00                       |
| Pad 3            | 42                 | 32.40.2B.00                       |
| Pad 4            | 46                 | 32.40.2F.00                       |
| Pad 5            | 49                 | 32.40.32.00                       |
| Pad 6            | 51                 | 32.40.34.00                       |
| Pad 7            | 54                 | 32.40.37.00                       |
| Pad 8            | 56                 | 32.40.39.00                       |
| Pad 9            | 36                 | 32.40.25.00                       |
| Pad 10           | 38                 | 32.40.27.00                       |
| Pad 11           | 41                 | 32.40.2A.00                       |
| Pad 12           | 45                 | 32.40.2E.00                       |
| Pad 13           | 48                 | 32.40.31.00                       |
| Pad 14           | 62                 | 32.40.3F.00                       |
| Pad 15           | 63                 | 32.40.40.00                       |
| Pad 16           | 64                 | 32.40.41.00                       |

Examples: Track 1 Pad 1 is key 37, so its base is 32.40.26.00. Track 1 Pad 9 is key 36, so its base is 32.40.25.00. A non-physical key such as key 22 has base 32.40.17.00 on Track 1.

## 5. Relationship to Roland Fantom and other ZEN-Core instruments

- The MC-101 base addresses differ from Fantom and other Roland ZEN-Core instruments. The important discovery is that many offsets inside blocks are reusable once the MC-101 base model is known.

- Tone partial offsets such as Level at 00.00.20.00, Pan at 00.00.20.07, Cutoff at 00.00.20.32, LFO blocks at 00.00.30.xx, and Tone Synth Partial offsets at 00.00.3E.xx align with the decoded ZEN/Fantom structures used as references.

- Drum Kit Partial offsets, for example Level +00.09, Pan +00.0A, Reverb Send +00.0C, Key Offset +00.0F and TVA offsets +00.15/+00.17/+00.19, match the PCMR_PTL-style layout seen in the Roland ZEN XML decode.

- Not every offset that exists in Fantom documentation is live or usable in the MC-101. The instrument identity fields for drum pads can be written/read back but did not reload the audible drum sound in testing. Matrix Control also showed MC-101-specific quirks.

## 6. Preset 5 Drum Kit Partial SysEx mappings

Preset 5 is the Drum Pad editor. Scenes 1 to 4 select Drum Tracks 1 to 4. The same CC positions are used in every scene, offset by 18 controls per nanoKONTROL scene. The table below shows the local CC position and the Drum Kit Partial offset applied to the selected drum key/pad.

| **Local control** | **Parameter**     | **Short** | **PCMR_PTL offset** | **Max** | **Encoding** | **Labels/values**      |
|-------------------|-------------------|-----------|---------------------|---------|--------------|------------------------|
| CC 0              | Pan               | PAN       | 00.00.00.0A         | 127     | 1            | labels 128             |
| CC 1              | Cutoff Offset     | CUT       | 00.00.00.11         | 200     | nibbles2     | values 201; labels 201 |
| CC 2              | Resonance Offset  | RES       | 00.00.00.13         | 200     | nibbles2     | values 201; labels 201 |
| CC 3              | Key Offset        | KEY       | 00.00.00.0F         | 48      | 1            | values 49; labels 49   |
| CC 4              | Fine Tune Offset  | FIN       | 00.00.00.10         | 100     | 1            | values 101; labels 101 |
| CC 5              | Output Assign     | OUT       | 00.00.00.0E         | 7       | 1            | labels 8               |
| CC 6              | Mute Group        | MUT       | 00.00.00.0D         | 31      | 1            |                        |
| CC 9              | Level             | LEV       | 00.00.00.09         | 127     | 1            |                        |
| CC 10             | Attack Offset     | ATK       | 00.00.00.15         | 200     | nibbles2     | values 201; labels 201 |
| CC 11             | Decay Offset      | DCY       | 00.00.00.17         | 200     | nibbles2     | values 201; labels 201 |
| CC 12             | Release Offset    | REL       | 00.00.00.19         | 200     | nibbles2     | values 201; labels 201 |
| CC 13             | Chorus/Delay Send | CHO       | 00.00.00.0B         | 127     | 1            |                        |
| CC 14             | Reverb Send       | REV       | 00.00.00.0C         | 127     | 1            |                        |

Scene CC numbers are local CC + scene offset: Scene 1 uses CC0..17, Scene 2 uses CC18..35, Scene 3 uses CC36..53, and Scene 4 uses CC54..71. Example: Pad Level is local CC9. It is CC9 on Scene 1, CC27 on Scene 2, CC45 on Scene 3 and CC63 on Scene 4.

## 7. Preset 6 Tone SysEx mappings

Preset 6 edits tone and partial parameters. Scenes include track and partial selection where applicable. Most CC mappings are partial-level sysex mappings and therefore use both selected track and selected partial. Mappings named sysex_track use the selected track and ignore the selected partial.

### 7.1 Preset 6 Scene 1: Common & Oscillator

| **Control** | **Parameter**     | **Short** | **Mapping type**        | **Offset(s)**            | **Max** | **Enc.** | **Condition / notes**   |
|-------------|-------------------|-----------|-------------------------|--------------------------|---------|----------|-------------------------|
| CC 0        | Osc Type          | OTY       | sysex                   | 00.00.3E.00              | 4       | 1        |                         |
| CC 1        | Wave Form         | WAV       | conditional sysex       | 00.00.3E.01              | 8       | 1        | if ('cc', 0)=1          |
| CC 2        | Detune            | DET       | conditional sysex       | 00.00.3E.08              | 127     | 1        | if ('cc', 0)=3          |
| CC 2        | Pulse Width       | PW        | conditional sysex       | 00.00.3E.06              | 127     | 1        | if ('cc', 0)=1          |
| CC 2        | Sync Wave         | WAV       | conditional sysex       | 00.00.3E.02              | 47      | 4        | if ('cc', 0)=2          |
| CC 2        | Wave Bank         | BNK       | conditional sysex       | 00.00.20.1C, 00.00.20.34 | 2       | 4        | if ('cc', 0)=0          |
| CC 3        | Pulse Width Depth | PWD       | conditional sysex       | 00.00.3E.07              | 126     | 1        | if ('cc', 0)=1          |
| CC 3        | Wave Number       | WAV       | conditional sysex       | 00.00.20.20, 00.00.20.38 | 257     | 4        | if ('cc', 0)=0, bank=10 |
| CC 3        | Wave Number       | WAV       | conditional sysex       | 00.00.20.20, 00.00.20.38 | 620     | 4        | if ('cc', 0)=0, bank=11 |
| CC 3        | Wave Number       | WAV       | conditional sysex       | 00.00.20.20, 00.00.20.38 | 963     | 4        | if ('cc', 0)=0, bank=8  |
| CC 4        | Structure 1-2     | ST1       | sysex track             | 00.00.3D.00              | 4       | 1        |                         |
| CC 5        | Md Depth          | MOD       | conditional sysex track | 00.00.3D.15              | 127     | 1        | if ('cc', 4)=4          |
| CC 5        | Mod Depth         | MOD       | conditional sysex track | 00.00.3D.08              | 10800   | 4        | if ('cc', 4)=3          |
| CC 5        | Ring Level        | RNG       | conditional sysex track | 00.00.3D.02              | 127     | 1        | if ('cc', 4)=2          |
| CC 6        | Structure 3-4     | ST3       | sysex track             | 00.00.3D.01              | 4       | 1        |                         |
| CC 7        | Mod Depth         | MOD       | conditional sysex track | 00.00.3D.0C              | 10800   | 4        | if ('cc', 6)=3          |
| CC 7        | Mod Depth         | MOD       | conditional sysex track | 00.00.3D.16              | 127     | 1        | if ('cc', 6)=4          |
| CC 7        | Ring Level        | RNG       | conditional sysex track | 00.00.3D.03              | 127     | 1        | if ('cc', 6)=2          |
| CC 8        | Analog Feel       | ANL       | sysex track             | 00.00.00.1C              | 127     | 1        |                         |
| CC 9        | Coarse Tune       | CRS       | sysex                   | 00.00.20.01              | 96      | 1        |                         |
| CC 10       | Fine Tune         | FIN       | sysex                   | 00.00.20.02              | 100     | 1        |                         |
| CC 11       | Level             | LEV       | sysex                   | 00.00.20.00              | 127     | 1        |                         |
| CC 12       | Pan               | PAN       | sysex                   | 00.00.20.07              | 127     | 1        |                         |
| CC 13       | Osc1 Level        | LV1       | conditional sysex track | 00.00.3D.04              | 127     | 1        | if ('cc', 4)=2          |
| CC 13       | Osc1 Level        | LV1       | conditional sysex track | 00.00.3D.10              | 127     | 1        | if ('cc', 4)=3          |
| CC 13       | Osc1 Level        | LV1       | conditional sysex track | 00.00.3D.10              | 127     | 1        | if ('cc', 4)=4          |
| CC 14       | Osc2 Level        | LV2       | conditional sysex track | 00.00.3D.05              | 127     | 1        | if ('cc', 4)=2          |
| CC 14       | Osc2 Level        | LV2       | conditional sysex track | 00.00.3D.11              | 127     | 1        | if ('cc', 4)=3          |
| CC 14       | Osc2 Level        | LV2       | conditional sysex track | 00.00.3D.11              | 127     | 1        | if ('cc', 4)=4          |
| CC 15       | Osc3 Level        | LV3       | conditional sysex track | 00.00.3D.06              | 127     | 1        | if ('cc', 6)=2          |
| CC 15       | Osc3 Level        | LV3       | conditional sysex track | 00.00.3D.12              | 127     | 1        | if ('cc', 6)=3          |
| CC 15       | Osc3 Level        | LV3       | conditional sysex track | 00.00.3D.12              | 127     | 1        | if ('cc', 6)=4          |
| CC 16       | Osc4 Level        | LV4       | conditional sysex track | 00.00.3D.07              | 127     | 1        | if ('cc', 6)=2          |
| CC 16       | Osc4 Level        | LV4       | conditional sysex track | 00.00.3D.13              | 127     | 1        | if ('cc', 6)=3          |
| CC 16       | Osc4 Level        | LV4       | conditional sysex track | 00.00.3D.13              | 127     | 1        | if ('cc', 6)=4          |
| CC 17       | Portamento Time   | TIM       | sysex track             | 00.00.00.24              | 1023    | 4        |                         |
| NOTE 4      | Structure Lock    | LCK       | conditional sysex track | 00.00.3D.14              | 1       | 1        | if ('cc', 4)=3          |
| NOTE 4      | Structure Lock    | LCK       | conditional sysex track | 00.00.3D.14              | 1       | 1        | if ('cc', 4)=4          |
| NOTE 6      | Structure Lock    | LCK       | conditional sysex track | 00.00.3D.14              | 1       | 1        | if ('cc', 6)=3          |
| NOTE 6      | Structure Lock    | LCK       | conditional sysex track | 00.00.3D.14              | 1       | 1        | if ('cc', 6)=4          |
| NOTE 7      | Unison            | UNS       | sysex track             | 00.00.3C.00              | 1       | 1        |                         |
| NOTE 8      | Mono/Poly         | M/P       | sysex track             | 00.00.00.1D              | 1       | 1        |                         |
| NOTE 13     | Partial Switch    | PSW       | dynamic sysex track     | 00.00.10.02              | 1       | 1        | partial 1               |
| NOTE 13     | Partial Switch    | PSW       | dynamic sysex track     | 00.00.10.0B              | 1       | 1        | partial 2               |
| NOTE 13     | Partial Switch    | PSW       | dynamic sysex track     | 00.00.10.14              | 1       | 1        | partial 3               |
| NOTE 13     | Partial Switch    | PSW       | dynamic sysex track     | 00.00.10.1D              | 1       | 1        | partial 4               |
| NOTE 16     | Portamento Mode   | PRM       | sysex track             | 00.00.00.21              | 1       | 1        |                         |
| NOTE 17     | Portamento Switch | PRT       | sysex track             | 00.00.00.20              | 1       | 1        |                         |

### 7.2 Preset 6 Scene 2: Filter & Envelope

CC18 is conditional: when Filter Model is TVF it edits TVF Filter Type; when Filter Model is VCF it edits VCF Type. CC31..34 switch between TVA envelope and Pitch envelope using Note D1 / the Amp/Pitch Env mode toggle.

| **Control** | **Parameter**     | **Short** | **Mapping type**    | **Offset(s)** | **Max** | **Enc.** | **Condition / notes** |
|-------------|-------------------|-----------|---------------------|---------------|---------|----------|-----------------------|
| CC 18       | TVF Filter Type   | TYP       | conditional sysex   | 00.00.20.31   | 6       | 1        | if ('cc', 22)=0       |
| CC 18       | VCF Type          | FTY       | conditional sysex   | 00.00.3E.12   | 4       | 1        | if ('cc', 22)=1       |
| CC 19       | Cutoff            | CUT       | sysex               | 00.00.20.32   | 1023    | 4        |                       |
| CC 20       | Resonance         | RES       | sysex               | 00.00.20.3D   | 1023    | 4        |                       |
| CC 21       | Filter Envelope   | ENV       | sysex               | 00.00.28.00   | 126     | 1        |                       |
| CC 22       | Filter Model      | FLT       | sysex               | 00.00.3E.0E   | 1       | 1        |                       |
| CC 23       | Key Follow        | KF        | sysex               | 00.00.20.36   | 400     | 4        |                       |
| CC 24       | Slope             | SLP       | sysex               | 00.00.3E.0F   | 2       | 1        |                       |
| CC 25       | High-pass Cutoff  | HPF       | conditional sysex   | 00.00.3E.0A   | 1023    | 4        | if ('cc', 22)=1       |
| CC 26       | Fat               | FAT       | sysex               | 00.00.3E.11   | 127     | 1        |                       |
| CC 27       | TVF T1 Attack     | F-A       | sysex               | 00.00.28.08   | 1023    | 4        |                       |
| CC 28       | TVF T3 Deacy      | F-D       | sysex               | 00.00.28.10   | 1023    | 4        |                       |
| CC 29       | TVF L3 Sustain    | F-S       | sysex               | 00.00.28.24   | 1023    | 4        |                       |
| CC 30       | TVF T4 Release    | F-R       | sysex               | 00.00.28.14   | 1023    | 4        |                       |
| CC 31       | Pitch Env Depth   | PED       | conditional sysex   | 00.00.24.00   | 200     | nibbles2 | if ('note', 26)=1     |
| CC 31       | TVA T1 Attack     | A-A       | conditional sysex   | 00.00.2C.04   | 1023    | 4        | if ('note', 26)=0     |
| CC 32       | Pitch Env Attack  | P-A       | conditional sysex   | 00.00.24.08   | 1023    | 4        | if ('note', 26)=1     |
| CC 32       | TVA T3 Deacy      | A-D       | conditional sysex   | 00.00.2C.0C   | 1023    | 4        | if ('note', 26)=0     |
| CC 33       | Pitch Env Sustain | P-S       | conditional sysex   | 00.00.24.24   | 1022    | 4        | if ('note', 26)=1     |
| CC 33       | TVA L3 Sustain    | A-S       | conditional sysex   | 00.00.2C.1C   | 1023    | 4        | if ('note', 26)=0     |
| CC 34       | Pitch Env Deacy   | P-D       | conditional sysex   | 00.00.24.10   | 1023    | 4        | if ('note', 26)=1     |
| CC 34       | TVA T4 Release    | A-R       | conditional sysex   | 00.00.2C.10   | 1023    | 4        | if ('note', 26)=0     |
| NOTE 31     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.02   | 1       | 1        | partial 1             |
| NOTE 31     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.0B   | 1       | 1        | partial 2             |
| NOTE 31     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.14   | 1       | 1        | partial 3             |
| NOTE 31     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.1D   | 1       | 1        | partial 4             |
| NOTE 35     | ADSREnv Switch    | ADS       | sysex               | 00.00.3E.10   | 1       | 1        |                       |

### 7.3 Preset 6 Scene 3: LFO 1/2

LFO1 starts at 00.00.30.00. LFO2 starts at 00.00.30.4F. Rate Note controls use reversed value lists so turning the knob up increases musical rate.

| **Control** | **Parameter**     | **Short** | **Mapping type**    | **Offset(s)** | **Max** | **Enc.** | **Condition / notes** |
|-------------|-------------------|-----------|---------------------|---------------|---------|----------|-----------------------|
| CC 36       | LFO1 Wave Type    | 1WT       | sysex               | 00.00.30.00   | 10      | 1        |                       |
| CC 37       | LFO1 Rate         | 1RT       | conditional sysex   | 00.00.30.04   | 1023    | 4        | if ('note', 42)=0     |
| CC 37       | LFO1 Rate Note    | 1RN       | conditional sysex   | 00.00.30.02   | 22      | 1        | if ('note', 42)=1     |
| CC 38       | LFO1 Delay Time   | 1DT       | sysex               | 00.00.30.0B   | 1023    | 4        |                       |
| CC 39       | LFO1 Fade Time    | 1FT       | sysex               | 00.00.30.12   | 1023    | 4        |                       |
| CC 40       | LFO2 Wave Type    | 2WT       | sysex               | 00.00.30.4F   | 10      | 1        |                       |
| CC 41       | LFO2 Rate         | 2RT       | conditional sysex   | 00.00.30.53   | 1023    | 4        | if ('note', 51)=0     |
| CC 41       | LFO2 Rate Note    | 2RN       | conditional sysex   | 00.00.30.51   | 22      | 1        | if ('note', 51)=1     |
| CC 42       | LFO2 Delay Time   | 2DT       | sysex               | 00.00.30.5A   | 1023    | 4        |                       |
| CC 43       | LFO2 Fade Time    | 2FT       | sysex               | 00.00.30.61   | 1023    | 4        |                       |
| CC 45       | LFO1 Amp Depth    | 1AD       | sysex               | 00.00.30.1B   | 200     | nibbles2 |                       |
| CC 46       | LFO1 Pan Depth    | 1PD       | sysex               | 00.00.30.1D   | 200     | nibbles2 |                       |
| CC 47       | LFO1 Filter Depth | 1FD       | sysex               | 00.00.30.19   | 200     | nibbles2 |                       |
| CC 48       | LFO1 Pitch Depth  | 1XD       | sysex               | 00.00.30.17   | 200     | nibbles2 |                       |
| CC 49       | LFO2 Amp Depth    | 2AD       | sysex               | 00.00.30.6A   | 200     | nibbles2 |                       |
| CC 50       | LFO2 Pan Depth    | 2PD       | sysex               | 00.00.30.6C   | 200     | nibbles2 |                       |
| CC 51       | LFO2 Filter Depth | 2FD       | sysex               | 00.00.30.68   | 200     | nibbles2 |                       |
| CC 52       | LFO2 Pitch Depth  | 2XD       | sysex               | 00.00.30.66   | 200     | nibbles2 |                       |
| NOTE 42     | LFO1 Rate Sync    | 1RS       | sysex               | 00.00.30.01   | 1       | 1        |                       |
| NOTE 43     | LFO1 Key Trigger  | 1KT       | sysex               | 00.00.30.16   | 1       | 1        |                       |
| NOTE 44     | LFO1 Fade Mode    | 1FM       | cycle sysex         | 00.00.30.11   | 3       | 1        |                       |
| NOTE 49     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.02   | 1       | 1        | partial 1             |
| NOTE 49     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.0B   | 1       | 1        | partial 2             |
| NOTE 49     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.14   | 1       | 1        | partial 3             |
| NOTE 49     | Partial Switch    | PSW       | dynamic sysex track | 00.00.10.1D   | 1       | 1        | partial 4             |
| NOTE 51     | LFO2 Rate Sync    | 2RS       | sysex               | 00.00.30.50   | 1       | 1        |                       |
| NOTE 52     | LFO2 Key Trigger  | 2KT       | sysex               | 00.00.30.65   | 1       | 1        |                       |
| NOTE 53     | LFO2 Fade Mode    | 2FM       | cycle sysex         | 00.00.30.60   | 3       | 1        |                       |

### 7.4 Preset 6 Scene 4: Matrix 1-4

Matrix Control is currently implemented using empirically shifted Tone Partial offsets. Matrix 1 starts at 00.00.20.5F in the current script rather than the nominal 00.00.20.56. Matrix 4 remains the least certain area: CC60/61/69 map to 00.00.20.7A/7B/7C, but testing suggested the MC-101 may not respond to all Matrix 4 fields consistently.

| **Control** | **Parameter**   | **Short** | **Mapping type**    | **Offset(s)** | **Max** | **Enc.** | **Condition / notes** |
|-------------|-----------------|-----------|---------------------|---------------|---------|----------|-----------------------|
| CC 54       | Matrix 1 Source | 1SC       | sysex               | 00.00.20.5F   | 108     | 1        |                       |
| CC 55       | Matrix 1 Dest   | 1DT       | sysex               | 00.00.20.60   | 48      | 1        |                       |
| CC 56       | Matrix 2 Source | 2SC       | sysex               | 00.00.20.68   | 108     | 1        |                       |
| CC 57       | Matrix 2 Dest   | 2DT       | sysex               | 00.00.20.69   | 48      | 1        |                       |
| CC 58       | Matrix 3 Source | 3SC       | sysex               | 00.00.20.71   | 108     | 1        |                       |
| CC 59       | Matrix 3 Dest   | 3DT       | sysex               | 00.00.20.72   | 48      | 1        |                       |
| CC 60       | Matrix 4 Source | 4SC       | sysex               | 00.00.20.7A   | 108     | 1        |                       |
| CC 61       | Matrix 4 Dest   | 4DT       | sysex               | 00.00.20.7B   | 48      | 1        |                       |
| CC 63       | Matrix 1 Sens   | 1SN       | sysex               | 00.00.20.61   | 126     | 1        |                       |
| CC 65       | Matrix 2 Sens   | 2SN       | sysex               | 00.00.20.6A   | 126     | 1        |                       |
| CC 67       | Matrix 3 Sens   | 3SN       | sysex               | 00.00.20.73   | 126     | 1        |                       |
| CC 69       | Matrix 4 Sens   | 4SN       | sysex               | 00.00.20.7C   | 126     | 1        |                       |
| NOTE 67     | Partial Switch  | PSW       | dynamic sysex track | 00.00.10.02   | 1       | 1        | partial 1             |
| NOTE 67     | Partial Switch  | PSW       | dynamic sysex track | 00.00.10.0B   | 1       | 1        | partial 2             |
| NOTE 67     | Partial Switch  | PSW       | dynamic sysex track | 00.00.10.14   | 1       | 1        | partial 3             |
| NOTE 67     | Partial Switch  | PSW       | dynamic sysex track | 00.00.10.1D   | 1       | 1        | partial 4             |

## 8. Non-SysEx mappings in the current script

The following are useful MC-101 controls in the script, but they are ordinary MIDI messages rather than System Exclusive:

- Transport Start/Stop use MIDI realtime messages rather than SysEx.

- Preset 7 Scatter pads send MIDI notes 60..75 on MIDI Channel 13. The current script holds the note while the physical button is held and sends note-off on release.

- Preset 7 Scenes 1..4 also send normal MIDI CCs on Channels 1..4 for track cutoff, resonance, pan, sends, knob macros, volume and envelope/vibrato controls.

- Preset 8 Scenes 1..4 provide a performance keyboard and ordinary MIDI CCs on Channels 1..4. Keyboard velocity defaults to 100 and is clamped to 10..120 in steps of 10.

## 9. Explored areas and caveats

- Drum Inst Number, Inst Bank and Inst Group ID are documented in the Drum Kit Partial block at +00..+08. They can be written and read back in SysEx dumps, but our MC-101 tests did not make the audible drum pad sound reload live. The current nanoKONTROL script therefore does not expose them as live controls.

- Drum Kit Partial documented size is 00.00.1B bytes. Each drum key starts on a 00.01.00 stride, leaving unused address space through +7F that could contain undocumented or reserved fields. We did not treat those as confirmed.

- Several readable aliases exist on the MC-101. A successful readback does not always mean the UI/audio engine has applied the change. The practical test is: write, read back, and confirm the sound/UI responds.

- Matrix Control required empirical adjustment. The nominal block appears in Tone Partial, but the current MC-101 behaviour suggested a one-block offset shift for useful Matrix 1..3 editing and ambiguous behaviour for Matrix 4.

- The Fantom/ZEN XML is a structural guide, not a guarantee that every field is active or live on MC-101 firmware.

## 10. Worked examples

### 10.1 Tone Partial Level on Track 2 Partial 1

Track 2 base = 30.42.00.00  
Partial 1 stride = 00.00.00.00  
Level offset = 00.00.20.00  
Final address = 30.42.20.00

### 10.2 Tone Partial Pan on Track 2 Partial 3

Track 2 base = 30.42.00.00  
Partial 3 stride = 00.00.02.00  
Pan offset = 00.00.20.07  
Final address = 30.42.22.07

### 10.3 Drum Pad Level on Track 1 Pad 1

Track 1 drum base = 32.40.00.00  
Pad 1 key = 37  
Key base = 32.40.26.00  
Level offset = 00.00.00.09  
Final address = 32.40.26.09

### 10.4 DT1 example: set Track 1 Pad 1 Level to 127

Address = 32 40 26 09  
Data = 7F  
Payload for checksum = 32 40 26 09 7F  
DT1 = F0 41 10 00 00 00 5E 12 32 40 26 09 7F 60 F7

## Appendix A. Matrix Source and Destination value maps

These labels are currently used for all four Matrix Source and Destination controls in Preset 6 Scene 4.

| **Source value** | **Source label** | **Destination value** | **Destination label** |
|------------------|------------------|-----------------------|-----------------------|
| 0                | OFF              | 0                     | OFF                   |
| 1                | CC01             | 1                     | PCH                   |
| 2                | CC02             | 2                     | CUT                   |
| 3                | CC03             | 3                     | RES                   |
| 4                | CC04             | 4                     | LEV                   |
| 5                | CC05             | 5                     | PAN                   |
| 6                | CC06             | 6                     | DLY                   |
| 7                | CC07             | 7                     | REV                   |
| 8                | CC08             | 8                     | PIT-LFO1              |
| 9                | CC09             | 9                     | PIT-LFO2              |
| 10               | CC10             | 10                    | TVF-LFO1              |
| 11               | CC11             | 11                    | TVF-LFO2              |
| 12               | CC12             | 12                    | TVA-LFO1              |
| 13               | CC13             | 13                    | TVA-LFO2              |
| 14               | CC14             | 14                    | PAN-LFO1              |
| 15               | CC15             | 15                    | PAN-LFO2              |
| 16               | CC16             | 16                    | LFO1-RATE             |
| 17               | CC17             | 17                    | LFO2-RATE             |
| 18               | CC18             | 18                    | PIT-ATK               |
| 19               | CC19             | 19                    | PIT-DCY               |
| 20               | CC20             | 20                    | PIT-REL               |
| 21               | CC21             | 21                    | TVF-ATK               |
| 22               | CC22             | 22                    | TVF-DCY               |
| 23               | CC23             | 23                    | TVF-REL               |
| 24               | CC24             | 24                    | TVA-ATK               |
| 25               | CC25             | 25                    | TVA-DCY               |
| 26               | CC26             | 26                    | TVA-REL               |
| 27               | CC27             | 27                    | PMT                   |
| 28               | CC28             | 28                    | FXM                   |
| 29               | CC29             | 29                    | MFX-CTRL1             |
| 30               | CC30             | 30                    | MFX-CTRL2             |
| 31               | CC31             | 31                    | MFX-CTRL3             |
| 32               | CC33             | 32                    | MFX-CTRL4             |
| 33               | CC34             | 33                    | PW                    |
| 34               | CC35             | 34                    | PWM                   |
| 35               | CC36             | 35                    | FAT                   |
| 36               | CC37             | 36                    | XMOD                  |
| 37               | CC38             | 37                    | LFO1_STEP             |
| 38               | CC39             | 38                    | LFO2_STEP             |
| 39               | CC40             | 39                    | SSAW-DETN             |
| 40               | CC41             | 40                    | PIT_DEPTH             |
| 41               | CC42             | 41                    | TVF-DEPTH             |
| 42               | CC43             | 42                    | TVA-DEPTH             |
| 43               | CC44             | 43                    | XMOD2                 |
| 44               | CC45             | 44                    | ATT                   |
| 45               | CC46             | 45                    | RING-OSC1-LEV         |
| 46               | CC47             | 46                    | RING-OSC2-LEV         |
| 47               | CC48             | 47                    | XMOD-OSC1-LEV         |
| 48               | CC49             | 48                    | XMOD-OSC2-LEV         |
| 49               | CC50             |                       |                       |
| 50               | CC51             |                       |                       |
| 51               | CC52             |                       |                       |
| 52               | CC53             |                       |                       |
| 53               | CC54             |                       |                       |
| 54               | CC55             |                       |                       |
| 55               | CC56             |                       |                       |
| 56               | CC57             |                       |                       |
| 57               | CC58             |                       |                       |
| 58               | CC59             |                       |                       |
| 59               | CC60             |                       |                       |
| 60               | CC61             |                       |                       |
| 61               | CC62             |                       |                       |
| 62               | CC63             |                       |                       |
| 63               | CC64             |                       |                       |
| 64               | CC65             |                       |                       |
| 65               | CC66             |                       |                       |
| 66               | CC67             |                       |                       |
| 67               | CC68             |                       |                       |
| 68               | CC69             |                       |                       |
| 69               | CC70             |                       |                       |
| 70               | CC71             |                       |                       |
| 71               | CC72             |                       |                       |
| 72               | CC73             |                       |                       |
| 73               | CC74             |                       |                       |
| 74               | CC75             |                       |                       |
| 75               | CC76             |                       |                       |
| 76               | CC77             |                       |                       |
| 77               | CC78             |                       |                       |
| 78               | CC79             |                       |                       |
| 79               | CC80             |                       |                       |
| 80               | CC81             |                       |                       |
| 81               | CC82             |                       |                       |
| 82               | CC83             |                       |                       |
| 83               | CC84             |                       |                       |
| 84               | CC85             |                       |                       |
| 85               | CC86             |                       |                       |
| 86               | CC87             |                       |                       |
| 87               | CC88             |                       |                       |
| 88               | CC89             |                       |                       |
| 89               | CC90             |                       |                       |
| 90               | CC91             |                       |                       |
| 91               | CC92             |                       |                       |
| 92               | CC93             |                       |                       |
| 93               | CC94             |                       |                       |
| 94               | CC95             |                       |                       |
| 95               | BEND             |                       |                       |
| 96               | AFT              |                       |                       |
| 97               | SYS-CTRL1        |                       |                       |
| 98               | SYS-CTRL2        |                       |                       |
| 99               | SYS-CTRL3        |                       |                       |
| 100              | SYS-CTRL4        |                       |                       |
| 101              | VELOCITY         |                       |                       |
| 102              | KEYFOLLOW        |                       |                       |
| 103              | TEMPO            |                       |                       |
| 104              | LFO1             |                       |                       |
| 105              | LFO2             |                       |                       |
| 106              | PIT-ENV          |                       |                       |
| 107              | TVF-ENV          |                       |                       |
| 108              | TVA-ENV          |                       |                       |

## Appendix B. Other notable value maps

| **Map**       | **Values**                                                                                                                                                                             |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Osc Type      | 0 PCM, 1 VA, 2 SYN, 3 SAW, 4 NOI                                                                                                                                                       |
| VCF Type      | 1 FLAT, 2 TYPE-JP, 3 TYPE-M, 4 TYPE-P                                                                                                                                                  |
| LFO Wave      | 0 SIN, 1 TRI, 2 SAW-UP, 3 SAW-DW, 4 SQR, 5 RND, 6 TRP, 7 S&H, 8 CHS, 9 VSIN, 10 STEP                                                                                                   |
| LFO Rate Note | 0 1/64T, 1 1/64, 2 1/32T, 3 1/32, 4 1/16T, 5 1/32., 6 1/16, 7 1/8T, 8 1/16., 9 1/8, 10 1/4T, 11 1/8., 12 1/4, 13 1/2T, 14 1/4., 15 1/2, 16 1T, 17 1/2., 18 1, 19 2T, 20 1., 21 2, 22 4 |
| LFO Fade Mode | 0 ON-IN, 1 ON-OUT, 2 OFF-IN, 3 OFF-OUT                                                                                                                                                 |
| Pan           | 0 L64, 64 C, 127 R63                                                                                                                                                                   |
| Matrix Sens   | 1 -63, 64 0, 127 +63                                                                                                                                                                   |

## Appendix C. Source script metadata

| **Item**                              | **Value**                                                   |
|---------------------------------------|-------------------------------------------------------------|
| Script analysed                       | 384bcfab-73a7-4346-83c9-1dc718ad871c.py                     |
| Copyright line                        | Copyright 2026 Ricardo Simoes; SPDX-License-Identifier: MIT |
| MC-101 SysEx model ID used by script  | 00 00 00 5E                                                 |
| Default device ID                     | 10                                                          |
| Main SysEx presets                    | Preset 5 Drum editor; Preset 6 Tone editor                  |
| Non-SysEx but MC-101-oriented presets | Preset 7 Scatter/CC; Preset 8 Keyboard/CC                   |