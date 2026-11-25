# OpenBokeh privacy policy

*Last updated: November 24, 2026*

**Summary: OpenBokeh does not collect, store or send any of your data. Everything happens on
your computer.**

## What OpenBokeh does with your image
- The webcam image is processed **only on your computer**, in memory, frame by frame.
- The result goes only to the “OpenBokeh Camera” virtual camera, which only the programs **you**
  choose (Meet, Zoom, OBS…) can read.
- No video frame is recorded to disk or sent to the internet.

## Noise-free microphone (optional, off by default)
- When it is on, the microphone sound is cleaned **only on your computer**, in 10 ms blocks in memory,
  and goes straight to the virtual audio cable (VB-CABLE). Nothing is recorded or sent.
- The “Record and listen” button keeps 4 seconds in memory only to play the test, then discards them.

## Screen recording (only when you start it)
- Videos are saved **only on your computer**, in the folder you choose (default: Videos\OpenBokeh).
- Nothing is sent. The app never records on its own: recording starts and stops with the button, menu or shortcut.
- On the "Record screen" page, the level meter uses the microphone only to show whether it is picking up sound:
  nothing is recorded. The microphone is released when you leave the page or minimize the app.

## Internet connection
- The installed version **does not connect to the internet**: the AI models come with the installer.
- There are no accounts, ads, telemetry, usage statistics or update checks.
- The only link to the web is the “Open VB-CABLE site” button, which opens your browser when you click it.

## What is stored on your computer
- Your settings (effect, adjustments, profiles, paths of the background images/videos you chose)
  are stored in `%APPDATA%\OpenBokeh\config.json`.
- A technical log (`openbokeh.log`) in the same folder, with error messages, to help solve problems.
  It contains no images; each time the app opens, the previous log becomes
  `openbokeh-anterior.log` (only the previous one is kept).
- The installer writes its steps to `%ProgramData%\OpenBokeh\instalacao.log` (only file names
  and result codes). It is deleted when uninstalling.
- When uninstalling, you can choose to delete this folder.

## Other programs
The call programs that receive the image from “OpenBokeh Camera” have their own privacy
policies, which do not depend on OpenBokeh.

## Open source
OpenBokeh is free software (GPL-3.0). Anyone can check in the source code that these statements
are true.
