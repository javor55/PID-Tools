#!/usr/bin/env bash
# Vytvoří release ke tagu (pokud ještě není). Tag s „b“, „beta“ nebo „rc“ (v3.2.0b1, v3.2.0-beta.1) = předběžná verze.
set -u
tag="$GITHUB_REF_NAME"
gh release view "$tag" >/dev/null 2>&1 && exit 0
pre=()
beta=""
if [[ "$tag" =~ (b[0-9]|beta|rc) ]]; then
  pre=(--prerelease)
  beta="**Beta version** – for testing. Calculations are the same as in the previous release, but the application and its installers are new: please check the results on your own data and report problems.

"
fi
notes="${beta}**Downloads (Windows 10/11, x64) – new application (PID Tools 4):**
- \`PID-Tools-*-setup.exe\` – installs the desktop application for the current user (no admin rights). If the Microsoft
  Edge WebView2 runtime is missing (rare on Windows 10/11), the installer downloads it.
- \`PID-Tools-*-setup-offline.exe\` – the same with the WebView2 runtime included, for PCs without internet.
- \`PID-Tools-*-x64.msi\` – for administrators / software distribution (silent: \`msiexec /i <file> /qn\`).
- \`SHA256SUMS.txt\` – checksums of the files.

Windows may warn that the publisher is unknown (the files are not code-signed yet): *More info › Run anyway*.
The new application opens older projects and saves format v3. Changes: see CHANGELOG.md. Deployment: docs/deployment.md."
target=()
[ -n "${RELEASE_TARGET:-}" ] && target=(--target "$RELEASE_TARGET")     # tag ještě neexistuje → vytvoří ho GitHub
gh release create "$tag" --title "PID Tools $tag" --notes "$notes" "${pre[@]}" "${target[@]}" || true
