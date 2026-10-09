# GT Pilot for BOSS

You play. It flies the pedalboard.

**Program a BOSS GT-1 with AI, just by talking.** GT Pilot (formerly Dial In) is a free, open source Claude Desktop extension (MCP server) that builds BOSS GT-1 patches from plain language: the sound of a song, an artist, an amp or just a feeling. Claude writes amp, drive and effects to the pedal over USB and keeps tweaking as you play. No menus, no BOSS Tone Studio editing, no settings to copy by hand.

Product page: [allankirsten.com/en/lab/gt-pilot](https://allankirsten.com/en/lab/gt-pilot) · Em português: [allankirsten.com/lab/gt-pilot](https://allankirsten.com/lab/gt-pilot)

Shape tones on a BOSS GT-1 by talking to Claude. Ask for the sound of a song, say it needs more drive or sounds muddy, and hear the pedal change while you play.

> "I want to play the Knee Socks solo" → Muff Fuzz into a Vox-style amp, subtle analog delay.
> "It sounds weird" → the modulation goes, the fuzz gets fuller.
> "It's too loud, neighbors" → the patch is leveled live while you play.

## What it can do

| | |
|---|---|
| Build and tweak tones | Every parameter of the loaded patch, live, with model names ("VO DRIVE", "MUFF FUZZ") |
| Listen | Records the GT-1 over USB and measures loudness, brightness, band balance and noise between phrases |
| Level volume | Adjusts the patch while you play until it sits at a steady level |
| Clean string noise | Raises the noise suppressor until the pauses are quiet, without touching your drive |
| Manage patches | List, load and save the 99 user slots |
| Practice | Metronome through the GT-1 output |

## Safety, by design

- Level parameters rise at most 15 per step.
- Switching patches never discards unsaved work without asking.
- Saving shows what is in the slot and waits for a yes. The old patch is backed up and the save is verified byte by byte.
- Every change in a conversation can be undone.

## Requirements

- macOS (tested on Apple Silicon, macOS 26)
- BOSS GT-1 connected over USB, with the [GT-1 driver](https://www.boss.info/global/products/gt-1/downloads/)
- BOSS TONE STUDIO for GT-1 **installed** (the extension reads its parameter map; the map is never redistributed). Keep the app **closed** while using the extension: it reloads the patch when it connects and does not see saves made from here.
- Claude Desktop

## Install

1. Download `gt-pilot.mcpb` from the [latest release](https://github.com/allankirsten/gt-pilot/releases/latest).
2. Double-click it and choose **Install** in Claude Desktop.
3. Connect the GT-1 and ask Claude: "check my GT-1".
4. The first time Claude listens, macOS asks for microphone access for Claude. Allow it: that is how the GT-1's USB audio is recorded.

## Updates

Once per session the extension reads a small public file that says whether a newer version exists, and Claude mentions it once with the link. The file is signed with an offline Ed25519 key and ignored unless the signature checks out. Nothing about you or your pedal is sent. Turn it off in the extension settings (**Check for new versions**).

To update, download the new `gt-pilot.mcpb` and open it: it replaces the old version and keeps your patch backups (`~/Library/Application Support/GT Pilot/backups`).

Coming from **Dial In** (0.2.x) or **GT-1 Conversational** (0.1.x)? Remove it in Claude Desktop (Settings > Extensions) before installing GT Pilot. Your backups move to the new folder on first run.

## Privacy

See [PRIVACY.md](PRIVACY.md). Short version: everything runs on your Mac; the only network request is the signed version check above.

## Build from source

```sh
uv sync
npx @anthropic-ai/mcpb pack
```

## Feedback

Bugs, ideas and "which pedal next" go to [Issues](https://github.com/allankirsten/gt-pilot/issues).

## License and notes

MIT, see [LICENSE](LICENSE). Made by [Allan Kirsten](https://allankirsten.com), designer and product leader ([LinkedIn](https://www.linkedin.com/in/allankirsten)), as part of his Lab. Not affiliated with BOSS or Roland Corporation. BOSS and GT-1 are trademarks of Roland Corporation. The GT-1 parameter map belongs to Roland and is never included here: it is read from BOSS TONE STUDIO on your own machine.
