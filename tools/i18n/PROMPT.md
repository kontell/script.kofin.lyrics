# Translation brief

This is the contract every `tr/<locale>.json` is written against.
Give this file, plus the worklist from `python3 tools/i18n/classify.py`, to whoever or whatever writes a locale.

## What you are translating

Kofin Lyrics shows song lyrics from a Jellyfin server in Kodi, either in a window of its own or through a skin that draws them.
Its strings are the add-on's summary and description, and the labels and help texts of its settings.
The reader is someone setting up lyrics on their TV, not a developer.

Translate the English `msgid` into the target language and write it as the value in `tr/<locale>.json`, keyed by the `msgctxt`.
Never alter a `msgid` — it is the lookup key Kodi matches on, and a changed one simply never resolves.

## Register

Use the register plugin.video.kofin's locales use, whose brief asks for Kodi's own.
German (`du`), Spanish (`tú`), Italian (`tu`), Dutch (`je`) and Polish address the user informally; French (`vous`), Russian, Ukrainian, Czech, Slovak, Greek, Romanian, Hungarian and Catalan use the formal form.
Match the locale's convention rather than importing English's.

Settings labels sit in a narrow column and stay short: a toggle reads as what it does ("Show lyrics automatically"), a value as a noun with its unit.
Help texts have a panel of their own and can be a sentence or two.

## Shared terms

plugin.video.kofin names this add-on in its own settings, and a viewer reads the two side by side.
Use the words that add-on's locale already uses:

| locale | lyrics | add-on | skin |
|---|---|---|---|
| ca_es | lletra, lletres | complement | aparença |
| cs_cz | text, texty skladeb | doplněk | vzhled |
| da_dk | sangtekst, sangtekster | tilføjelse | skin |
| de_de | Songtext, Songtexte | Add-on | Skin |
| el_gr | στίχοι | πρόσθετο | κέλυφος |
| es_es, es_mx | letra, letras | complemento | skin |
| fi_fi | sanoitukset | lisäosa | ulkoasu |
| fr_fr, fr_ca | paroles | extension | habillage |
| hu_hu | dalszöveg | kiegészítő | skin |
| it_it | testo, testi | add-on | skin |
| ja_jp | 歌詞 | アドオン | スキン |
| ko_kr | 가사 | 애드온 | 스킨 |
| nb_no | sangtekst, sangtekster | tillegg | skall |
| nl_nl | songtekst, songteksten | add-on | skin |
| pl_pl | tekst, teksty | dodatek | skórka |
| pt_pt, pt_br | letra, letras | add-on | skin |
| ro_ro | versuri | supliment | interfață |
| ru_ru | текст, тексты песен | дополнение | обложка |
| sk_sk | text, texty piesní | doplnok | vzhľad |
| sv_se | låttext, låttexter | tillägg | skin |
| uk_ua | текст, тексти пісень | додаток | скін |
| zh_cn | 歌词 | 插件 | 皮肤 |
| zh_tw | 歌詞 | 外掛 | 外觀佈景 |

Prefer the term the locale's Kodi UI already uses for anything else Kodi names, such as *seconds* or *pixels*.

## Never translate

Jellyfin, Kodi, Kofin, Kofin Lyrics.

## Notes on particular ids

- `#30002` — *the lyrics button* is the button a skin's player controls offer for bringing lyrics up.
- `#30003`, `#30004` — *timings* are the times each line is sung at. Lyrics without them cannot follow the song, so they stay still. Say it the way the locale says synced and unsynced lyrics.
- `#30005`, `#30006` — the offset moves every line later (positive) or earlier (negative). *Raise it* and *lower it* mean the setting's value.
- `#30010` — keep the numbers 480 and 800: they are values of the setting. *The now-playing info* is the track information a skin shows while music plays, at the bottom of the screen.

## Honesty

These are machine translations. Each generated file carries

```
# Note: machine-translated (LLM), pending native review.
```

in its header. That line stays until a native speaker has actually reviewed the file. It is what stops the next reader assuming this has been checked.
