#!/usr/bin/env bash
# Vytvoří release ke tagu (pokud ještě není). Tag s „b“, „beta“ nebo „rc“ (v3.2.0b1, v3.2.0-beta.1) = předběžná verze.
set -u
tag="$GITHUB_REF_NAME"
gh release view "$tag" >/dev/null 2>&1 && exit 0
pre=()
beta=""
if [[ "$tag" =~ (b[0-9]|beta|rc) ]]; then
  pre=(--prerelease)
  beta="**Beta version** – for testing. Calculations are the same as in the previous release, but the Windows packages (installer, portable and web offline ZIP) are new: please check the results on your own data and report problems.

"
fi
notes="${beta}**Downloads (Windows 10/11, x64):**
- \`PID-Tools-*-setup.exe\` – installs the desktop application for the current user (no admin rights, Start menu, uninstall in Settings › Apps).
- \`PID-Tools-*-desktop-win64-portable.zip\` – the desktop application without installing: unzip and run \`PID Tools.exe\`.
- \`PID-Tools-*-web-win64-offline.zip\` – the web app on this PC without internet: unzip and run \`PID-Tools.bat\`.

Windows may warn that the publisher is unknown (the files are not code-signed): *More info › Run anyway*.
Changes: see CHANGELOG.md. Deployment: docs/deployment.md."
gh release create "$tag" --title "PID Tools $tag" --notes "$notes" "${pre[@]}" || true
