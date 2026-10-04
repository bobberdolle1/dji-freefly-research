# Parameter catalogue — `assets/params_catalog.json`

Stage 6. Every claim here is read directly from the asset inside the APK.
Regenerate with:

```
python tools/analyze_params_catalog.py \
    work/apktool/decoded/assets/params_catalog.json work/generated
```

The asset is proprietary and is **not** committed. This document describes it;
the machine-readable summary lands in the gitignored `work/generated/`.

---

## 1. Shape

**FACT.** The asset is a single JSON **array of 855 objects**, each with
exactly three keys — no more, no less:

| Key | Meaning | Range observed |
|---|---|---|
| `i` | index | `12 … 1472`, **all 855 unique**, no duplicates |
| `t` | type id | `0, 1, 2, 4, 5, 8, 9` (see below) |
| `n` | name | DJI-style dotted path, or `alias|canonical` |

There is **no table number**. This is a single flat index space, which
corroborates the 2017 protocol's index-addressed design: `(table, index)` in
the request reduces to an index here.

**FACT.** The index space is **sparse**: 855 entries occupy a range of 1473,
with 99 gaps. The lowest entry is index 12; indices 0–11 are absent.

---

## 2. Type distribution

Type ids match the app's `ParamType` enum ordinals exactly (see
`research/flylib/params.py`):

| Id | Type | Count | Share |
|---|---|---|---|
| 0 | `UINT8` | 344 | 40.2 % |
| 8 | `FLOAT` | 326 | 38.1 % |
| 5 | `INT16` | 82 | 9.6 % |
| 1 | `UINT16` | 57 | 6.7 % |
| 2 | `UINT32` | 30 | 3.5 % |
| 4 | `INT8` | 8 | 0.9 % |
| 9 | `DOUBLE` | 8 | 0.9 % |
| 3 | `UINT64` | 0 | — |
| 6 | `INT32` | 0 | — |
| 7 | `INT64` | 0 | — |

**INFERENCE.** `UINT8` and `FLOAT` dominate because most of the catalogue is
flags and sensor/gain tuning rather than user-facing values. The complete
absence of 64-bit and 32-bit signed integers is consistent with a catalogue
collected from consumer aircraft rather than from a full firmware dump.

### The catalogue's index space is not a table

There is **no table number** in the asset — only `{i, t, n}` — so this is a
single flat index space.

**INFERENCE (open).** That flat space is *consistent with* the 2017 protocol
being index-addressed, but the join is **not pinned**: the code mapping a
catalogue index to the `(tableNo, paramIndex)` pair used by `loadIndexMap` /
`readByIndexMap` has not been traced. Whether `i` is a global index or a
per-table index that happens to be globally unique is therefore
**unresolved**, and every index must be treated as model-specific until that
join is found.


---

## 3. Aliases — the `|` convention

**FACT.** 64 of the 855 entries (7.5 %) use a pipe-separated form:

```
"n": "<short friendly name>|<canonical DJI parameter path>"
```

Example: `"go_home_height|g_config.go_home.fixed_go_home_altitude"`.

**INFERENCE.** The left side is a stable, UI-facing short name; the right side
is the real DJI parameter path. The app can therefore display a friendly name
while writing to the canonical parameter — which is also what makes the
short names usable as 2015-protocol hash preimages. Several aliases appear in
*both* directions: `"g_config.flying_limit.radius_limit_enabled|g_config.
advanced_function.radius_limit_enabled"` puts a DJI path on the left, so the
convention is not strictly "friendly name first". **The separator convention is
reproduced, not assumed**, in `flylib` and in the generated report.

---

## 4. Families

**FACT.** Grouping by the leading path component:

| Family | Count |
|---|---|
| `g_config` | 118 |
| `imu0` | 31 |
| `imu1` | 31 |
| `g_status` | 22 |
| `fault_sum_history` | 20 |
| `device_gyr_acc` | 10 |
| `imu_cali_0/1/2` | 5 each |
| `g_cfg_debug` | 4 |

**INFERENCE.** `g_config` is the writable configuration family and is where a
parameter editor earns its keep; `imu*`, `device_gyr_acc` and `fault_sum_history`
are mostly read-only telemetry and fault history. Array-indexed parameters
appear as `g_config.fdi_sensor[0..2]` and `imu_cali_N.acc_gyro[N]`.

---

## 5. The region parameters — the important finding

**FACT.** The catalogue contains exactly two CE (regulatory) parameters:

| Index | Type | Name |
|---|---|---|
| **687** | **`UINT32`** | **`ce_country_type`** |
| **858** | **`UINT8`** | **`ce_regulatory_level`** |

**FACT.** Keyword searches over all 855 names find **zero** occurrences of:
`region`, `fcc`, `c0`, `geo`, `nfz`, `no_fly`, `droneid`, `drone_id`, `4g`,
`cefc`.

### What this means

**INFERENCE.** Free Fly reaches region settings through the **FC parameter
protocol**, not through an FCC command sequence. `ce_country_type` is a
firmware-level country parameter that the 2017 protocol addresses as
`(table, index)` and the 2015 protocol addresses by name hash. Since Free Fly
implements both read and write for both protocols, the *mechanism* it uses is
the generic parameter editor, while the *effect* can be a region change.

This is the crux of the comparative question and it cuts against a too-simple
answer in both directions:

- **It is not** an FCC tool. There is no radio-region command, no FCC profile,
  no service-mode sequence, no RCLink framing anywhere in the APK.
- **It is not** merely a benign parameter browser either. It can enumerate and,
  through its write path, address the country/regulatory parameters that FCC
  tools also target — by a different route.

**HYPOTHESIS.** Free Fly and the FCC tools may be **mechanism-disjoint but
effect-overlapping**: they reach the same class of firmware state through
different protocols. What would settle it: a byte-level comparison of
Free Fly's `writeParamValue2017(table, 687, value)` against the FCC profiles
recovered from the public corpus, and confirmation of which table number
carries index 687 on a real aircraft. Note that the index space here is flat
and model-specific — the same index need not be the same parameter on a
different airframe, so any cross-tool frame comparison must pin the
airframe.

---

## 6. Feature families the brief asked about

**FACT**, with representative entries:

**Flight limits**
`g_config.flying_limit.max_radius` (UINT16, 654) ·
`max_height` (655) · `user_set_max_height` (656) ·
`radius_limit_enabled` (657, aliased) · `roof_limit_enable` (669) ·
`avoid_ground_and_smart_landing_enable` (662)

**RTH / failsafe**
`go_home_height|g_config.go_home.fixed_go_home_altitude` (27) ·
`go_home_heading` (28) · `avoid_enable` (30) ·
`avoid_ascending_height_limit_disable` (34) · `go_home_finish_radius` (36) ·
`rc_lost_action|g_config.fail_safe.protect_action` (612) ·
`RC_ARM_STOP_ENABLE|g_config.rc_cfg.arm_action_enable` (417)

**Obstacle avoidance** — 24 entries
`enable_horizontal_obstacle_avoidance` (685) ·
`enable_downward_vision_position_and_avoidance` (683) ·
`enable_avoid_ground_protection` (684) · `user_avoid_enable` (817) ·
`user_down_avoid_enable` (818) · `user_back_avoid_enable` (819) ·
`bypass_sub_mode` (820) · `vert_up/down_avoid_min_dis_m`

**VPS / downward vision**
`vps_func_en|g_config.mvo_cfg.mvo_func_en` (1022) ·
`enable_downward_vision_position_and_avoidance` (683)

**GPS / RTK**
`gps_enable|g_config.gps_cfg.gps_enable` (244) ·
`miss_rtk_use_rtk_data` (278) · `rtk_fix_last` (279) ·
`fscap_gnss_source_mode_app_enable` (270)

**ATTI**
`g_config.mode_atti_normal_cfg` (8 entries) · `avoid_atti_range` (772) ·
`use_mode_normal_cfg_for_mode_atti` (800) · `brake_plan_atti_max` (859) ·
`tilt_atti_roll_range` / `tilt_atti_pitch_max` (893/894)

**Battery protection**
`dji_bat_level_1|g_config.voltage2.level_1_voltage` (1040) ·
`dji_bat_level_2` (1041) · `raw_bat_level_1|g_config.voltage.level_1_protect`
(1045) · `raw_bat_level_2` (1046) ·
`enSmartBatGH|g_config.voltage2.user_set_smart_bat` (1039)

**Control gains** — the classic tuning set
`basic_gain_roll_usr|g_config.control.basic_roll` (1142) · `basic_pitch` (1143) ·
`g_config.control.basic_tail` (1144) ·
`g_config.control.atti_vertical|g_config.control.basic_thrust` (1145) ·
`horiz_pos_gain` (1321) · `horiz_vel_gain` (1325)

**Statistics**
`g_status.user_info.statistical_info.total_distance` (12) ·
`total_motor_start_time` (13) · `total_powerup_times` (14) ·
`total_fly_times` (15) — plus a parallel `..._last` set

**Gimbal** — 5 entries: `gimbal_yaw_back_to_middle_en` (862) ·
`gimbal_down_on_landing_en` (863) · `gimbal_fixed_angle` (866) and two more

---

## 7. Statistics

| Metric | Value |
|---|---|
| Entries | 855 |
| Unique indices | 855 (no collisions) |
| Index range | 12 – 1472 |
| Occupancy of range | 855 / 1473 ≈ 58 % |
| Gaps in index space | 99 |
| Aliased entries | 64 (7.5 %) |
| Distinct type ids used | 7 of 10 |
| Distinct top-level families | ~30 |

---

## 8. A raw FC parameter is not a Drone-Hacks feature

This distinction matters for the comparative report and is stated plainly:

- `ce_country_type` being **present in the catalogue** proves Free Fly can
  *enumerate* it. It does **not** prove the app presents a region UI, and it
  certainly does not prove the value can be written successfully — the FC
  Assistant write path may reject it, may require an unlock, or may accept and
  ignore it.
- Reading a parameter and changing firmware behaviour are different claims.
  Only the second is a "hack".
- The catalogue is the app author's **inventory of what exists**, not a
  statement of what the app's UI exposes or what the aircraft accepts.