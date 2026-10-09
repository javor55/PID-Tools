"""
Společné prvky vzhledu (podle návrhu) pro všechny záložky: karta hlavní plochy s nadpisem, řádek panelu
„popisek vlevo, pole vpravo“, nápověda „?“ a dlaždice hodnot (Ms, GM, PM …). Tabulky: pidtools.ui.table.
"""
import html

import streamlit as st


def q(help_):
    """Kroužek „?“ s nápovědou po najetí myší."""
    return f"<span class='q' title='{html.escape(help_, quote=True)}'>?</span>" if help_ else ""


def card(key):
    """Bílá karta hlavní plochy (rámeček, zaoblení) – kontejner."""
    return st.container(key=f"pid_card_{key}")


def head(title, help_=None, note=None, right=None, cont=None):
    """Nadpis karty: název 15 px tučně, „?“, poznámka šedě vedle, volitelně text vpravo (HTML)."""
    s = (f"<div class='pid-chead'><span class='t'>{html.escape(title)}</span>{q(help_)}"
         + (f"<span class='n'>{note}</span>" if note else "")
         + (f"<span class='r'>{right}</span>" if right else "") + "</div>")
    (cont or st).markdown(s, unsafe_allow_html=True)


def lrow(label, help_=None, ratio=(1.0, 2.2), cont=None):
    """Řádek panelu: popisek (+ „?“) vlevo, vrací sloupec pro pole vpravo (pole se popiskem „collapsed“)."""
    c0, c1 = (cont or st).columns(list(ratio), vertical_alignment="center")
    c0.markdown(f"<div class='pid-plab'>{html.escape(label)}{q(help_)}</div>", unsafe_allow_html=True)
    return c1


def tiles(items, cont=None):
    """
    Dlaždice hodnot vedle sebe: items = [(popisek, hodnota, doplněk, úroveň)], úroveň "ok" / "warn" / "bad" / None
    (zelená / jantarová / červená / neutrální).
    """
    cells = "".join(f"<div class='pid-tile {lvl or ''}'><div class='l'>{html.escape(lbl)}</div>"
                    f"<div class='v'>{html.escape(val)}</div>"
                    + (f"<div class='s'>{html.escape(sub)}</div>" if sub else "") + "</div>"
                    for lbl, val, sub, lvl in items)
    (cont or st).markdown(f"<div class='pid-tiles' style='grid-template-columns: repeat({len(items)}, 1fr)'>"
                          f"{cells}</div>", unsafe_allow_html=True)


def level(v, good, warn, lower_better=True):
    """Úroveň dlaždice podle mezí (menší = lepší, nebo naopak)."""
    if v is None:
        return None
    if lower_better:
        return "ok" if v <= good else ("warn" if v <= warn else "bad")
    return "ok" if v >= good else ("warn" if v >= warn else "bad")
