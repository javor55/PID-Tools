# Nasazení veřejné instance PID Tools (Oracle Cloud Free Tier + Cloudflare Tunnel)

Návod krok za krokem. Výsledek: `https://pidtools.<vase-domena>` běží na ARM64 VM v Oracle Cloud, bez otevřených
portů (provoz jde přes Cloudflare Tunnel), a sám se aktualizuje po každém pushi do větve `deploy`.

```
push do větve deploy ──> GitHub Actions: build + test (amd64+arm64) ──> ghcr.io/javor55/pid-tools:deploy
                                                                              │ (Watchtower, každých 5 min)
návštěvník ──> Cloudflare (WAF, TLS) ──> tunel ──> cloudflared ──> app:8080 <──┘
```

Soubory: `compose.yml` (služby `app`, `cloudflared`, `watchtower`), `.env.example` (nastavení). Všechny proměnné
aplikace (limity veřejného režimu apod.) jsou v [docs/deployment.md](../docs/deployment.md).

## 1. VM v Oracle Cloud

1. Vytvořte instanci **VM.Standard.A1.Flex** (ARM64 / aarch64, Always Free; např. 4 OCPU a 24 GB RAM), image
   **Ubuntu 22.04 nebo 24.04**, přidejte svůj SSH klíč.
2. V *Security List* / *NSG* nechte příchozí jen **SSH (22)**. Žádný port 80/443/8080 otvírat nemusíte – tunel
   navazuje spojení směrem ven. Oracle image mají navíc předvyplněná pravidla `iptables`; kdyby SSH nešlo, nemažte je,
   jen ověřte, že je port 22 povolený.
3. Připojte se a nainstalujte Docker:
   ```bash
   ssh ubuntu@<ip-vm>
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER && newgrp docker
   docker compose version        # Compose v2 je součástí instalace
   ```
4. Automatické bezpečnostní aktualizace systému:
   ```bash
   sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
   ```
   (Oracle Linux: `sudo dnf install -y dnf-automatic && sudo systemctl enable --now dnf-automatic-install.timer`.)

## 2. Cloudflare Tunnel

1. Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel** → typ **Cloudflared**,
   název např. `pidtools`.
2. Na stránce *Install and run connectors* zkopírujte **token** (dlouhý řetězec za `--token`). Instalovat nic dalšího
   nemusíte – `cloudflared` běží v Dockeru. Token je heslo, nikam ho nesdílejte.
3. Záložka **Public Hostname** → *Add*: subdoména `pidtools`, doména vaše, **Service**: typ `HTTP`, URL **`app:8080`**
   (název služby v `compose.yml` a port, na kterém aplikace poslouchá). Cloudflare sám vytvoří DNS záznam a TLS certifikát.
4. Doporučená ochrana (zdarma):
   - **Security → WAF → Rate limiting rules**: např. 100 požadavků / 10 s na IP pro hostname `pidtools.<domena>`,
     akce *Block* nebo *Managed challenge*.
   - **Security → Bots → Bot Fight Mode**: zapnout.
5. **Cloudflare Access není pro veřejný režim potřeba** (aplikace je záměrně otevřená, každý návštěvník dostane
   anonymní relaci s limity). Access použijete jen u týmové varianty (`PIDTOOLS_AUTH=cloudflare`, viz docs/deployment.md).

## 3. GitHub: větev `deploy` a obraz

1. Vytvořte větev `deploy` z `main` a pushněte ji:
   ```bash
   git switch -c deploy main && git push -u origin deploy
   ```
   Push spustí workflow **Web image** (`.github/workflows/web-image.yml`): sestaví obraz pro amd64 i arm64, odzkouší
   ho (health + vytvoření pracovního prostoru), proskenuje (Trivy; selže na CRITICAL s dostupnou opravou) a nahraje do
   `ghcr.io/javor55/pid-tools` s tagy `deploy`, `latest` a `sha-<krátký hash>`. První běh trvá cca 15–25 minut
   (arm64 se emuluje přes QEMU), další díky cache obvykle 8–15 minut.
2. **Viditelnost balíčku** – po prvním běhu: GitHub → váš profil/organizace → **Packages** → `pid-tools` →
   **Package settings** → *Change visibility* → **Public**. Pak VM nepotřebuje žádné přihlášení.
3. **Soukromý balíček** (varianta): vytvořte *Personal access token (classic)* s jediným právem **`read:packages`**
   a v `.env` na VM vyplňte `GHCR_USER` (uživatel GitHub) a `GHCR_TOKEN`. Při prvním stažení se ještě jednou přihlaste:
   `echo <PAT> | docker login ghcr.io -u <uzivatel> --password-stdin`. Watchtower dostane přihlášení z `.env`
   (`REPO_USER` / `REPO_PASS`); alternativně odkomentujte v `compose.yml` připojení `~/.docker/config.json`.

## 4. Spuštění na VM

```bash
git clone --depth 1 --filter=blob:none --sparse --branch deploy https://github.com/javor55/pid-tools.git
cd pid-tools && git sparse-checkout set deploy && cd deploy
cp .env.example .env
nano .env                     # doplňte TUNNEL_TOKEN (případně limity a GHCR_*)
docker compose up -d
docker compose ps             # app by měla být "healthy", cloudflared "running"
docker compose logs -f        # Ctrl+C ukončí výpis
```
(U soukromého repozitáře klonujte s PATem nebo soubory `compose.yml` a `.env.example` prostě zkopírujte přes `scp`.)
Otevřete `https://pidtools.<vase-domena>`. V Cloudflare Tunnels má tunel stav **Healthy**.

## 5. Aktualizace a návrat

- **Aktualizace:** merge / push do větve `deploy` → workflow postaví obraz (viz výše) → **Watchtower** každých 5 minut
  (`WATCHTOWER_INTERVAL`) zkontroluje `:deploy`, stáhne novou verzi a restartuje jen kontejner `app` (štítek
  `com.centurylinklabs.watchtower.enable`) a smaže starý obraz. Hotovo do ~5 minut po dokončení workflow. Při restartu
  se zahodí rozpracované relace (aplikace drží vše v paměti).
- **Návrat:** vrácením (revert) commitu na `deploy` a pushem, nebo okamžitě přichycením na starší obraz – v `.env`
  `PIDTOOLS_IMAGE=ghcr.io/javor55/pid-tools:sha-<hash>` a `docker compose up -d`. Watchtower pak hlídá jen tento tag
  (nepřepíše ho na novější).
- Ruční aktualizace: `docker compose pull && docker compose up -d`.
- Změna `compose.yml` / `.env` (git pull ve složce `deploy`) se projeví po `docker compose up -d`.

## 6. Provoz

- **Zálohy:** veřejný režim je bezstavový (nic se neukládá na disk, vše je v paměti a v `tmpfs`), zálohovat se nemusí
  nic kromě souboru `.env` (uložte si token jinde, jde ale vygenerovat znovu v Cloudflare).
- **Logy:** `docker compose logs -f app` (řádek na požadavek, začátek a konec úloh); rotace je nastavena (3 × 10 MB).
- **Stav:** `docker compose ps` (healthcheck), v Cloudflare Zero Trust stav tunelu; volitelně bezplatný monitoring
  (např. UptimeRobot) na `https://pidtools.<domena>/health`.
- **Oracle Free Tier a nečinné instance:** Oracle může nečinné instance Always Free s velmi nízkým využitím CPU / paměti
  / sítě po určité době (uvádí se 7 dní) uvolnit. Předejít tomu může lehká pravidelná zátěž nebo převod účtu na Pay As
  You Go (Always Free zdroje zůstávají zdarma). Aktuální podmínky ověřte v dokumentaci Oracle.
- **Bezpečnost:** kontejnery běží bez práv (`cap_drop: ALL`, `no-new-privileges`, `read_only`), aplikace nepublikuje
  žádný port. Watchtower má přístup k Docker socketu (běží jen on, nic jiného nezpřístupňuje) – pokud vám to vadí,
  aktualizujte ručně a službu `watchtower` z `compose.yml` odstraňte.

## 7. Řešení potíží

| Příznak | Příčina / postup |
|---|---|
| `docker compose up` hlásí `doplňte TUNNEL_TOKEN` | prázdný token v `.env` |
| `exec format error` | stažen obraz pro jinou architekturu; ověřte `docker image inspect ... --format '{{.Architecture}}'` (má být `arm64`) a že workflow postavil oba platformy |
| `pull access denied` / `unauthorized` | balíček je soukromý – nastavte jej jako Public, nebo viz bod 3.3 |
| Web vrací Cloudflare chybu 1033 / 502 | `docker compose ps`: běží `cloudflared` a je `app` healthy? Public hostname musí mít službu `http://app:8080` |
| `app` je `unhealthy`, restartuje se | `docker compose logs app` – nejčastěji chybná proměnná v `.env` (aplikace při startu ověřuje konfiguraci) |
| Po nasazení se nic nemění | workflow ještě běží / selhal (záložka Actions); `docker compose logs watchtower` |
| Watchtower: `client version ... is too old` | použijte `nickfedor/watchtower` (už je v `compose.yml`), ne starý `containrrr/watchtower` |
| Chyba „read-only file system“ v logu app | aplikace zapisuje mimo `/tmp` – nahlaste; dočasně lze v `compose.yml` odstranit `read_only` |
| Nelze se připojit přes SSH | pravidla `iptables` v Oracle image / Security List, viz bod 1.2 |
| Docker spotřebuje disk | `docker system prune -af` (Watchtower s `--cleanup` maže staré obrazy sám) |
