#!/usr/bin/env python3
"""Shared visual tokens for every page this project publishes (chart pages via build-artifact.py, the journal via
journal.py render). One palette, both themes, so the pages read as one product. Method-lane colours: --w Wyckoff,
--i ICT, --f Footprint, --h Heatmap; semantic --up/--down/--warn are separate from the accent."""
FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap">'
TOKENS = r""":root{
  --bg:#F3F5F8; --surface:#FFFFFF; --surface-2:#F7F9FB; --surface-3:#EDF1F5;
  --line:#DCE2EA; --line-strong:#C5CED9;
  --ink:#172029; --ink-2:#3D4955; --muted:#5F6B79; --faint:#6B7784;
  --up:#1F8F5F; --down:#CF3F55; --up-soft:#D9F0E4; --down-soft:#F8DEE2;
  --warn:#B5731C; --warn-soft:#FBEBD3;
  --w:#B8801F; --w-soft:#F7EBD2; --i:#4C5BC7; --i-soft:#E3E6F9; --f:#1F8C85; --f-soft:#D8EFEC; --h:#7E4FB3; --h-soft:#EBE0F6;
  --accent:#2F5FC9;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace; --sans:'Manrope',system-ui,-apple-system,'Segoe UI',sans-serif;
  --shadow:0 1px 2px rgba(23,32,41,.06),0 6px 20px rgba(23,32,41,.05);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#0E1218; --surface:#151B23; --surface-2:#1B222C; --surface-3:#222B36;
  --line:#28313D; --line-strong:#39465A;
  --ink:#E7EBF0; --ink-2:#C2CAD5; --muted:#97A3B4; --faint:#8592A2;
  --up:#3FBF7F; --down:#EF5C70; --up-soft:#173A2B; --down-soft:#3E1F27;
  --warn:#E0A54A; --warn-soft:#3A2A12;
  --w:#D79A2E; --w-soft:#33270F; --i:#7C8BE8; --i-soft:#222846; --f:#3BB8AF; --f-soft:#123634; --h:#B285E0; --h-soft:#2E2140;
  --accent:#7FA4F5; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  --bg:#0E1218; --surface:#151B23; --surface-2:#1B222C; --surface-3:#222B36;
  --line:#28313D; --line-strong:#39465A;
  --ink:#E7EBF0; --ink-2:#C2CAD5; --muted:#97A3B4; --faint:#8592A2;
  --up:#3FBF7F; --down:#EF5C70; --up-soft:#173A2B; --down-soft:#3E1F27;
  --warn:#E0A54A; --warn-soft:#3A2A12;
  --w:#D79A2E; --w-soft:#33270F; --i:#7C8BE8; --i-soft:#222846; --f:#3BB8AF; --f-soft:#123634; --h:#B285E0; --h-soft:#2E2140;
  --accent:#7FA4F5; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
}
"""
