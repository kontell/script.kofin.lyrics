# Translations

**The translations here are machine-generated (LLM) and tagged `pending native review` in each file header.**
They are a starting point, not a substitute for a native speaker's pass.

This is plugin.video.kofin's toolchain, so the two add-ons are translated the same way and into the same 26 locales.

`resources/language/resource.language.en_gb/strings.po` is the English source.
In every other locale file the `msgid` stays English (it is the lookup key) and only `msgstr` is filled in.
Kodi auto-discovers `resource.language.*` directories and falls back to English for any string a locale does not translate, so a partial or absent translation never regresses anything.

There is no translation service involved: the translations are authored by hand or by a model into `tr/<locale>.json`, and `gen.py` renders them into `.po` files.
`PROMPT.md` is the brief those translations are written against.

## Layout

```
PROMPT.md          the translation brief -- read this before writing a locale
classify.py        PASSTHROUGH allowlist + the worklist dumper
po_lib.py          PO parsing, escaping, and the template renderer
gen.py             LANG_META + the only thing that writes a .po
validate.py        structural check on generated files
pocheck.py         well-formedness + placeholder/bbcode preservation
tr/_source.json    the English text each translation was made from
tr/<locale>.json   ctx -> translated msgstr, 26 locales
```

Everything is stdlib-only and lives under `tools/`, which `tools/build.py` leaves out of the add-on zip.

## Generating

```bash
python3 tools/i18n/gen.py                 # every locale in LANG_META
python3 tools/i18n/gen.py de_de fr_fr     # named locales
python3 tools/i18n/gen.py --check         # write nothing; fail if any locale is stale
python3 tools/i18n/validate.py            # structural
python3 tools/i18n/pocheck.py             # well-formedness + placeholders
```

Where gettext is installed, the authoritative syntax check is:

```bash
for f in resources/language/resource.language.*/strings.po; do
  msgfmt -c -o /dev/null "$f"; done
```

Output is deterministic — `REVISION_DATE` in `gen.py` is fixed — so regenerating with no data change produces no diff.
`gen.py --check` relies on that: it renders every locale in memory and fails unless the files on disk match, so a hand-edited `.po`, or a JSON change that was never rendered, cannot merge.
CI's `translations` job runs it with both validators, and so does `tox -e translations`.

## Why the renderer copies the source line by line

`po_lib.render()` walks the English file and substitutes `msgstr` values in place, rather than rebuilding each entry from parsed data.
That makes every locale structurally identical to the source for free: the same entries, in the same order, with the same spacing.
Comments stay in the English file only; they are notes for whoever writes a translation, which happens in `tr/<locale>.json`.

## The `_source.json` snapshot

`gen.py` hard-fails when a key is missing from a locale.
That catches an *added* string but not a *reworded* one: the translation is still present and still valid-looking, it just now describes something else.
That is not hypothetical — pvr.kofin's 26 locales once went two English revisions stale on one string, and it took a manual audit to find.

So `tr/_source.json` records the English text every translation was made from, and `gen.py` refuses to write when the current source disagrees with it.
Restamping it is a deliberate act that asserts "the locales now match the English":

```bash
python3 tools/i18n/gen.py --snapshot
```

The snapshot is shared across all locales, so a reworded string invalidates every locale at once.
That is the correct blast radius, but it does mean you cannot restamp after fixing only some of them.

## Adding or changing an English string

1. Prefer a Kodi core string where Kodi already has the word: it is already translated into every language. The settings category uses Kodi's `#128`, *General*, this way.
2. Edit `resources/language/resource.language.en_gb/strings.po` as usual.
3. If the new entry is a bare technical token, add its id to `PASSTHROUGH` in `classify.py` and stop — the generator supplies `msgstr == msgid` itself.
4. Otherwise add the key to all 26 `tr/<locale>.json` files. `gen.py` lists exactly what is missing, so this cannot drift silently.
5. `python3 tools/i18n/gen.py --snapshot`
6. `python3 tools/i18n/gen.py && python3 tools/i18n/validate.py && python3 tools/i18n/pocheck.py`
7. Commit the English source, the JSONs and the generated `.po` files together.

Rewording an existing string means step 4 as well — `gen.py` will say so.

## The add-on's summary and description

Kodi shows these from `addon.xml`, not from the language files.
The `Addon Summary` and `Addon Description` entries keep them translated alongside everything else.
`addon.xml` carries the same text for every locale: its en_GB text matches the English source, and each other `lang` matches that locale's msgstr.
Nothing generates those tags, so a reworded summary or description has to be copied into `addon.xml` by hand.

## Adding a locale

1. Add an entry to `LANG_META` in `gen.py` — locale key, `Language:` header value, `Language-Team` name, and the correct `Plural-Forms` for that language.
2. Write `tr/<locale>.json` with a translation for every non-passthrough entry (`classify.py` prints the worklist).
3. `python3 tools/i18n/gen.py <locale> && python3 tools/i18n/validate.py <locale> && python3 tools/i18n/pocheck.py <locale>`

The directory is created for you. No packaging change is needed: `tools/build.py` ships `resources/language/**` wholesale.

## `OK_IDENTICAL`

`validate.py` treats a `msgstr` equal to its `msgid` as an untranslated leftover, because that is usually what it is.
`OK_IDENTICAL` is the escape hatch for words a locale legitimately keeps in English.
Add to it only after checking that the locale really does use the English word.
