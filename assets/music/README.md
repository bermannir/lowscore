# Music

Drop music files in this folder (`.ogg`, `.mp3` or `.wav`). The game picks them up
automatically: no code changes needed. Volume is set in **Settings → Music**.

## Which file plays where

Files are matched by how their names **start** (upper/lower case doesn't matter):

| File name starts with | Plays during |
|---|---|
| `Modal Drift` | Title screen, settings, hero select, story scenes, level complete, victory and game over |
| `War` | Battle. Sorted by name: level 1 plays the 1st, level 2 the 2nd, and so on (wrapping around when there are more levels than tracks). The boss fight plays the last one. |

Exact duplicate files (e.g. `War Drum Heartbeat.wav` and `War Drum Heartbeat (1).wav`
with identical content) are only counted once.

## Overriding a single part

A file with one of these exact names wins over the rules above:

| File name | Plays during |
|---|---|
| `menu.ogg` | Menus and story |
| `level1.ogg` … `level4.ogg` | That level |
| `level.ogg` | Any level without its own `levelN` file |
| `boss.ogg` | The final wave with the Ember Demon |
| `default.ogg` | Anything above that has no file of its own |

Each track loops until the game moves to a part that uses a different track, and
tracks cross-fade when they change.
