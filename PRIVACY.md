# Privacy

Dial In runs entirely on your Mac.

**What it touches on your machine**
- The BOSS GT-1, over USB (MIDI to read and change patches, USB audio when Claude listens to measure level and noise).
- The parameter map inside BOSS TONE STUDIO for GT-1, copied to `~/Library/Application Support/Dial In`.
- Patch backups, saved in the same folder before any slot is overwritten.

**Audio.** When you ask Claude to listen, a few seconds of the GT-1 output are recorded and turned into numbers (loudness, brightness, noise). The recording is not stored or sent anywhere; only the numbers go back into the conversation.

**Network.** One request per session to `https://allankirsten.com/lab/dial-in/latest.json` to check for a newer version. It sends no identifiers, no data about you, your pedal or your patches. You can turn it off in the extension settings (**Check for new versions**).

**Your conversation** is between you and Claude, under Anthropic's terms. Dial In adds tool results (patch names, parameter values, measurements) to it, nothing else.

**No telemetry, no analytics, no accounts.**

Questions: open an issue at https://github.com/allankirsten/dial-in/issues.
