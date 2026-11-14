# Girl Agent Love

[中文](README.md) · **English**

Girl Agent Love is a framework that uses Ren'Py as the engine and lets AI write the story in real time. You can use it to build a galgame of your own.

**Current version: 1.0-b.1**

## Contents

- [Project structure](#project-structure)
- [Character cards and worldview](#character-cards-and-worldview)
- [Images](#images)
- [Audio](#audio)
- [Saves and records](#saves-and-records)
- [Subagent mode](#subagent-mode)
- [Self-healing mode](#self-healing-mode)
- [Copyright and license](#copyright-and-license)
- [How to use](#how-to-use)
- [About maintaining this framework](#about-maintaining-this-framework)
- [FAQ](#faq)

## Project structure

```
.
├── options.txt
├── README.md
├── LICENSE / NOTICE / THIRD_PARTY_NOTICES.md
├── game/
│   ├── ai.rpy / script.rpy / screens.rpy / options.rpy
│   ├── seikai.md
│   ├── persona/<english id>.md
│   ├── picture/scene/<day|dusk|night>_<location>.jpg
│   ├── picture/standing/<character id>/<number>.webp
│   ├── picture/ui/
│   ├── bgm/<number>.<format> + bgm.md
│   ├── voice/<character id>/<number>.wav
│   ├── voice_example/<character name or id>.wav
│   ├── voice_ids.json
│   ├── opening.json
│   └── time_words.json (optional)
├── savedata/
│   ├── slot_<n>.json / .png
│   ├── history.json
│   ├── chapters.json
│   ├── diary/<character>.json
│   └── harness/
└── skills/girl-agent-love-config/
```

`ai.rpy` handles model calls, prefetching, the story tree, re-injection, subagents, diary, harness, and image generation. `script.rpy` handles sprite registration, the render loop, the save/load UI, and the dynamic stage.

## Character cards and worldview

Character cards go in `game/persona/<english id>.md`, one file per character. The file name must match the frontmatter `id`, and files starting with an underscore are not loaded. `me.md` is the player character.

Common frontmatter fields:

```yaml
---
id: aya
name: aya
gender: female
aliases: \\[murasame, murasame sama]
lead: true
romance: true
affection: 0
voice\\_name: Serena
---
```

1. `lead` marks the heroine, `romance` decides whether affection is tracked, and `affection` is the starting value.
2. If a character has a special way of addressing someone, put it in that speaker's own card. For example, *Tomotake Yoshino* calls *Murasame* 「Murasame sama」, so you write it in their `## Character details` section like this:

```markdown(Tomotake Yoshino character details)
Calls Murasame 「Murasame sama」
```

```markdown(Murasame character details)
Most people call me 「Murasame sama」 besides 「Goshujin」. I think it's too formal, but I never asked them to stop.
```

Otherwise the model and the engine can't connect and you'll get a bug.

3. `gender` is only `female` or `male`.
4. `voice\\_name` is only used with Alibaba Cloud Bailian TTS to choose a fixed voice. You can ignore it for cloned voices.
5. The body is written in four sections: an opening paragraph, character details, appearance and body language, and sprites. Character details is fed to the model whole, so the more specific it is the better. You can look at Bangumi, Moegirlpedia, and similar wikis for reference (please don't copy). In appearance and body language, the more detail you write, the more accurate sprite generation becomes and the more accurately the story and sprites are produced. **Sprites must use numeric ids.**

Example:

```markdown
### Sprite 1

id: 1
clothes: kimono girl
pose: standing, hands folded in front
expression: mouth open, eyes wide, looking surprised
when to use: everyday moments when she is surprised

id: 2
clothes: school uniform girl
pose: standing, hands folded in front
expression: mouth open, eyes wide, looking surprised
when to use: surprised while wearing the school uniform
```

6. `game/seikai.md` is the worldview, written in seven sections: synopsis, era and place, world rules, main locations, character relationships, taboos and boundaries, current situation. The main locations must match the locations under `picture/scene/` (fuzzy match).

## Images

### Sprites

1. Put them in `picture/standing/<character id>/<number>.webp`. Formats: `png`, `jpg`, `webp`.
2. No expression variations. If you need different expressions, store a separate sprite for each expression under the same outfit and describe them in the character card.

### Backgrounds

Backgrounds go in `picture/scene/<time>\\_<location>.jpg`. The time is always one of day, dusk, night. Formats: `png`, `jpg`.

## Audio

### Voice

1. **There is no unified interface for voice models. The current integrations support *Alibaba Cloud Bailian*, *mimo*, and *OpenAI*. If you use another voice API, adapt it following its documentation. Voice generation is slow, so voice can fall behind the model; if that happens, increase the lead time.**
2. For cloned voices, save the cloned voice as `<character english id>.wav` in `voice\\_example/`.

### BGM

1. Supports `mp3`, `ogg`, `wav`, `m4a`.
2. Save BGM as `<number>.<format>` in `bgm/` and register how each id is used in `bgm.md`.

## Saves and records

Saves, history, and diaries live in `savedata/` in the project directory and are created on first launch. Story history is not trimmed by beat count, so long sessions keep growing; archive or clear `savedata/` manually if you need to control its size.

## Subagent mode

1. Each non-player persona card gets its own subcall that only sees its own card, the worldview, `game/agent.md`, and the last `GALGAME_HISTORY_FEED` beats of global history; the parent model adds narration, reorders beats, writes choices, and fills in lines verbatim according to `game/director.md`. **In theory** this is more realistic.
2. The feature can introduce bugs from uneven subagent latency and from subagents returning errors; in that case the framework lowers quality to keep the game going.
3. With subagents off, one model handles all the text, which is more stable.
4. `game/director.md` and `game/agent.md` can be edited directly; if missing or empty, built-in rules are used. Re-injection is by global history beat count: every `GALGAME_REINJECT_EVERY` beats, each card, the worldview, and the rule files are promoted to full text.

## Self-healing mode

`option.txt` has a built-in self-healing switch. When enabled, a healing model checks for errors in the background and fixes them on the fly, ~~keeping the game playable~~.

If you launch through harness, you can ignore this setting. It's off by default. If it's off and you launch through harness, self-healing still works through the harness model. If it's on and you launch through harness, the built-in model in option runs self-healing instead of the harness model. If you don't want harness self-healing, just tell harness — it has a hard switch too.

## Copyright and license

### Ren'Py license

Ren'Py is MIT plus portions under LGPL. A distributed game must include `game/LICENSE.txt`, keep the renpy.org license link, and must not prevent users from replacing the engine. The script doesn't have to be open source.

### About this framework's license

This framework is released under the Apache 2.0 license. When you publish a game made with it, include the framework notice and the Ren'Py notice.
This program contains free software licensed under a number of licenses, including the GNU Lesser General Public License. A complete list of software is available at http://www.renpy.org/doc/html/license.html.

### Also

1. Images in a work may be AI-generated; check the generation service's terms before commercial use. Characters and scripts must be original. Use licensed BGM and credit it on the About page.
2. Please respect the copyright of all visual novels. The author does not recommend using this framework to copy other visual novels. All examples are just examples and do not mean the author copied them or encourages copying them.

## How to use

### Method 1

Install Ren’Py 8.5.3. Download the framework ZIP from [GitHub Releases](https://github.com/ACEyumoooo/Girl-Agent-Love/releases) and extract it in full. Set the Ren’Py Launcher’s projects directory to the parent of the extracted project, then select the project and launch it.

General settings go in `options.txt` at the project root, and API credentials go in `key.txt`. For installations already using a fallback settings directory, use the in-game Settings screen. Keep real credentials in your local project copy and use the blank credential template for commits and sharing.

### Method 2

Hand it to an agent (AI) and let the project's skill guide you through it.

## About maintaining this framework

The author is a third-year student outside computer science, busy with experiments and classes . I write scripts, and most of this is Python, which I can still read — though my Python is about "hello world" level, and a good half of this was written by AI.

The author might set up a superagent to maintain it, but right now that's not really possible: no money, and servers plus feeding several subagents is hard to afford. But I really will consider it!

So without a superagent, I'll find time to read what's in the issues and batch updates to make the framework better!

Early releases will probably have a pile of bugs, so expect rapid updates during the first month.

## FAQ

Q: Can I make a female-oriented work?
A: Of course. Even though the framework says "girl", you can tell your AI "I want a female-oriented one" and it will adapt. The default protagonist is male and the romanceable characters are female.

Q: Can I publish a work together with the framework, even commercially?
A: Yes. The framework itself is under the Apache 2.0 open-source license, which allows free use, modification, and redistribution, including commercial distribution alongside your work; your characters, sprites, backgrounds, scripts, and BGM are yours and you can publish or sell them, as long as you comply with Apache 2.0 and the Ren'Py license. That said, please don't republish the framework under a new name as your own original work, and don't use it to copy someone else's work. For Ren'Py, check and follow its license.

