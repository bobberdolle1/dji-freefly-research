#!/usr/bin/env bash
# Toolchain bootstrap: fetches a portable JRE 17, jadx and apktool into work/tools.
# Idempotent. Nothing here is committed (work/ is gitignored).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/work/tools"
mkdir -p "$TOOLS"

if [ ! -d "$TOOLS/jdk" ]; then
  echo "[toolchain] fetching Temurin JRE 17..."
  curl -sSL -o "$TOOLS/jdk.zip" \
    "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse"
  unzip -q -o "$TOOLS/jdk.zip" -d "$TOOLS"
  mv "$(ls -d "$TOOLS"/jdk-*/ | head -1)" "$TOOLS/jdk"
  rm -f "$TOOLS/jdk.zip"
fi

if [ ! -f "$TOOLS/lib/jadx-cli-all.jar" ] && [ ! -f "$TOOLS/lib/jadx-1.5.2-all.jar" ]; then
  echo "[toolchain] fetching jadx 1.5.2..."
  curl -sSL -o "$TOOLS/jadx.zip" \
    "https://github.com/skylot/jadx/releases/download/v1.5.2/jadx-1.5.2.zip"
  unzip -q -o "$TOOLS/jadx.zip" -d "$TOOLS"
  rm -f "$TOOLS/jadx.zip"
fi

if [ ! -f "$TOOLS/apktool.jar" ]; then
  echo "[toolchain] fetching apktool 2.11.1..."
  curl -sSL -o "$TOOLS/apktool.jar" \
    "https://bitbucket.org/iBotPeaches/Apktool/downloads/apktool_2.11.1.jar"
fi

export JAVA_HOME="$TOOLS/jdk"
JADX_JAR="$(ls "$TOOLS"/lib/jadx-*.jar 2>/dev/null | head -1)"
echo "[toolchain] JAVA_HOME=$JAVA_HOME"
"$JAVA_HOME/bin/java" -jar "$JADX_JAR" --version
"$JAVA_HOME/bin/java" -jar "$TOOLS/apktool.jar" --version
echo "[toolchain] ready"