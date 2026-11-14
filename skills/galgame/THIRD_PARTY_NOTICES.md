# Third-party notices

This file lists third-party components that ship with or are used by the
galgame Ren'Py framework. The Apache License 2.0 in the root `LICENSE` covers
the original framework code only. It does not relicense Ren'Py, its bundled
libraries, the fonts, or the default GUI images.

## Ren'Py

- Project: Ren'Py visual novel engine
- Copyright: Tom Rothamel and contributors
- License: MIT for most of the engine, with portions under the GNU Lesser
  General Public License (LGPL)
- Full license and component list: `game/LICENSE.txt`
- Online: https://www.renpy.org/doc/html/license.html
- LGPL source repositories: https://github.com/renpy/renpy and
  https://github.com/renpy/renpy-build

Ren'Py's license asks you to include a copy of its license with every copy you
distribute, and to link to the license from your README or store description.
The suggested wording is:

> This program contains free software licensed under a number of licenses,
> including the GNU Lesser General Public License. A complete list of software
> is available at http://www.renpy.org/doc/html/license.html.

Do not block users from replacing the Ren'Py engine files. If you distribute a
built game, keep `game/LICENSE.txt` next to it.

## Fonts

- Source Han Sans Lite
- Copyright 2014-2025 Adobe, with Reserved Font Name "Source"
- License: SIL Open Font License 1.1
- Full text: `game/fonts/LICENSE-OFL.txt`

## Ren'Py default GUI

The images under `game/gui/` come from the default Ren'Py project template.
They remain under the Ren'Py license, not the Apache License 2.0. Replace them
with your own art before releasing if you want a distinct look.

## Python and bundled libraries

Ren'Py binaries include Python and other libraries such as FFmpeg, chardet,
Fribidi, libusb, Pygame_SDL2, SDL2, FreeType, libpng, and zlib. The complete
list and their licenses are in `game/LICENSE.txt`. Some of them are LGPL; the
source repositories are listed there.

## Generated content

Images, voice files, and story text generated with a model or voice service are
not covered by the framework's Apache License. Check the terms of the service
you use before commercial release. Characters, scripts, music, and other assets
you add are your responsibility.

## Apache License 2.0 notes

If you modify framework files and distribute the result, Apache License 2.0
section 4(b) asks you to add a prominent notice stating that you changed the
files. Keep the copyright, patent, trademark, and attribution notices that come
with the framework. The license does not grant permission to use the project's
name or logos as trademarks.
