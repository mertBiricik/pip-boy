# Band 8 watchface format notes

Findings from getting a mibandwatchfaces.com maker export to run on a Xiaomi Smart Band 8 (`miwear.watch.m66gl`) through Gadgetbridge. Everything below was checked on the band unless marked otherwise.

## What the maker exports

`wfDef.json` + `images/` + `images_aod/` + a preview. This is a source project for Xiaomi's WatchfacePackTool, not an installable file. Gadgetbridge needs a compiled `.bin` (magic `5A A5 34 12`).

## Pitfalls when packing with Mi8WfBinTool

Packing the export as-is gives a face that shows only its background, with the AOD falling back to the firmware's default clock.

1. **`imageIndexList` is required for every `widge_imagelist`.** It is the value-to-image table. The maker omits it, and the packer then writes the widget without a table. Values per data source (from Mi-Create's `sources.json`):
   - `0A11` / `0911` / `1211` / `1111` (hour/minute digits): `0..9`
   - `2012` weekday: `0..6`, 0 = Sunday
   - `3041` screen lock, `1841` sleep, `0813` AM/PM: `0..1`
2. **Definition indices must be dense.** Each table (single images, image lists, widgets) is indexed `0..n-1` in order of first use, and the firmware reads the index as a table position. Mi8WfBinTool pins the index from file names matching `image_NNNN` / `imagelist_NNNN`, and the maker's names are sparse, so references fall outside the tables. `tools/build.py` renames assets to `sNN` / `lNN_MM` in a staging copy.
3. **Header bytes (precaution, not isolated).** A firmware-accepted Band 8 binary (Pzqqt's Colorful Lines) has `0x1E = 4` and byte 3 of every face header (`0xA8 + i*0x58`) set to `2`. The packer writes `6` and `0`. The build copies the reference values. It is untested whether the band actually needs this; items 1 and 2 were the ones that fixed it.

## Other observations

- **`element_anim` does not work on the Band 8.** The EasyFace wiki says so ("Animations do not work for MB8 and MB7Pro(Global)"). On the band it plays as noise.
- **A 60-entry image list on the seconds source (`1811`) broke the whole face** (background only, ~630 KB file). Not investigated further.
- **Filled AOD digits are allowed.** Xiaomi's own "Mecha" face uses filled AOD digits. The "AOD digits must be outlined" advice found in some guides is not a hard rule.
- **`widge_dignum` bytes 14–15** hold a rotation angle (0 for upright digits). Inferred from the reference binary, not tested on the band.
- **Weather** on the face comes from whatever the phone last sent. With Gadgetbridge that needs a weather provider app, for example Breezy Weather → Settings → External modules → Send Gadgetbridge data.
