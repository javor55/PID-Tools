"""Pomocník e2e testů: rozbalovací nabídky lišty prohlížeče záznamu (viewer.js) – jejich položky jsou mimo DOM, dokud nabídka není otevřená."""


def menu(pg, root, name, open_=True):
    """Nabídka lišty grafu (mode | view | cur | exp) se otevře / zavře; hledá se uvnitř root (selektor hostitele grafu)."""
    sel = f'{root} [data-testid="vw-m-{name}"]'
    if (pg.locator(sel).get_attribute("aria-expanded") == "true") != open_:
        pg.locator(sel).click()
    pg.wait_for_selector(f'{sel}[aria-expanded="{"true" if open_ else "false"}"]')
    pg.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="attached" if open_ else "detached")
