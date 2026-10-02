"""
Aplikační vrstva: stav projektu a pracovní postup (data → model → ladění → scénář → APC → protokol) bez vazby
na konkrétní UI. Používá ji webový frontend (Streamlit, pidtools.ui) i desktopový frontend (Qt,
pidtools.desktop); výpočty jsou v pidtools.core. Modul nesmí importovat streamlit ani Qt (hlídá test).

Moduly:
  dataio       – načtení CSV/Excel, čas, převzorkování, kontrola komprese
  dataset      – rozložení tabulky (wide, pairs, long) → signály → společná časová mřížka, ukázková data
  guess        – odhad role sloupců (PV, MV, SP, poloha) podle názvů a průběhů
  loop         – převody jednotek (NormPV / NormMV), konfigurace bloku PIDConL a sad parametrů
  scenario     – scénář simulace: události → průběhy, délka simulace, proces a ventil, ukazatele
  feedforward  – dopředná vazba: výchozí návrh a parametry pro simulaci
  model        – identifikace, přepočet rozsahu, úpravy, hodnocení, validace a nejistota modelu
  tuning       – metody ladění, návrh parametrů, srovnání metod, robustnost sad
  apc          – výpočty pokročilých struktur (doporučení, Smith, gain scheduling, FF, decoupling)
  project      – formát projektu (JSON) společný pro všechny frontendy
"""
