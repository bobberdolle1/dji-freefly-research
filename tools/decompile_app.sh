#!/usr/bin/env bash
# Targeted JADX decompile of Free Fly's own classes.
#
# A full `jadx -d out <apk>` run spent 30+ minutes in codegen without emitting a
# single file: the APK carries 14,580 classes, almost all AndroidX/Compose/Hilt.
# The research target is ~15 hand-written classes, so they are decompiled one at
# a time with --single-class, which only pays for the class actually requested.
#
# Output lands in work/jadx/app/ and is regenerated on demand; smali from
# apktool remains the authoritative evidence for protocol constants.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK="$ROOT/samples/FF_v_1_00.apk"
OUT="$ROOT/work/jadx/app"
TOOLS="${FF_TOOLS:-$ROOT/../work/tools}"
JAVA_HOME="${FF_JAVA_HOME:-$TOOLS/jdk-17.0.20.1+1-jre}"
JADX_JAR="$(ls "$TOOLS"/lib/jadx-*.jar | head -1)"

CLASSES=(
  com.dronehacks.app.DroneHacksApp
  com.dronehacks.app.MainActivity
  com.dronehacks.app.di.AppModule
  com.dronehacks.app.ui.screens.MainViewModel
  com.dronehacks.app.ui.screens.UiState
  com.dronehacks.app.data.repository.DroneRepository
  com.dronehacks.app.data.repository.RepoResult
  com.dronehacks.app.data.usb.UsbSerialManager
  com.dronehacks.app.data.usb.UsbState
  com.dronehacks.app.data.protocol.DroneCommands
  com.dronehacks.app.data.protocol.DumlBuilder
  com.dronehacks.app.data.protocol.DumlConstants
  com.dronehacks.app.data.protocol.DumlHeader
  com.dronehacks.app.data.protocol.DumlPacket
  com.dronehacks.app.data.protocol.DumlParser
  com.dronehacks.app.data.model.ConnectionState
  com.dronehacks.app.data.model.DroneInfo
  com.dronehacks.app.data.model.DroneParameter
  com.dronehacks.app.data.model.ParamCatalog
  com.dronehacks.app.data.model.ParamCategory
  com.dronehacks.app.data.model.ParamDef
  com.dronehacks.app.data.model.ParamType
  com.dronehacks.app.data.model.ParamValueType
)

mkdir -p "$OUT"
for cls in "${CLASSES[@]}"; do
  dest="$OUT/$(echo "$cls" | tr '.' '/').java"
  if [ -s "$dest" ]; then
    echo "skip   $cls"
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  echo "decomp $cls"
  "$JAVA_HOME/bin/java" -Xmx2g -jar "$JADX_JAR" \
      --single-class "$cls" --single-class-output "$dest" \
      --show-bad-code "$APK" >/dev/null 2>&1 || echo "  WARN: failed $cls"
done

echo "--- decompiled: $(find "$OUT" -name '*.java' | wc -l) / ${#CLASSES[@]}"