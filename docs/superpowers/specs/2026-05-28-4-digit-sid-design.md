# 4-digit `sid` encoding (`SRII`)

**Date:** 2026-05-28
**Status:** Approved (design)
**Scope:** `config/nexus9000v/` only — the VM generator, the 16 per-switch YAMLs, and the 10 `con_*` console helpers.

## Problem

`sid` is today a flat 2-digit integer (`1–255`). It is consumed in three places that each
impose a hidden width constraint:

- **MAC generation** drops `sid` into a *single octet* via `f"{base_mac}:{sid:02x}:..."`.
  One octet holds `0x00–0xFF`, so a value wider than two hex digits produces a malformed,
  non-unique MAC.
- **Telnet / monitor ports** are built by *string concatenation* — `f"90{sid:02d}"` and
  `f"44{sid:02d}"`. A 4-digit sid yields a 6-digit number (e.g. `901501`) far above the
  65535 TCP-port ceiling.
- **Validation** hard-caps `sid` at `1–255`.

We want `sid` to encode **site + role + index** in four digits. That is incompatible with all
three consumers as written, so each needs a redesign — not merely a wider field.

## Goal

Make `sid` a 4-digit `SRII` value that cleanly encodes site, role, and a per-(site,role)
index, while keeping every derived artifact (MACs, ports, console helpers) unique and legal.

## The `SRII` scheme

```
sid = site×1000 + role×100 + index
```

- **site** — single digit `1–9`.
- **role** — single digit, reusing the existing role codes: `3 = BG`, `4 = SP`, `5 = LE`, `6 = TOR`.
- **index** — two digits `01–99`, numbered per (site, role).

This matches the lab's existing `site·role·index` convention already used in the mgmt-IP last
octet (loosely coupled, hand-maintained — out of scope here) and in the site-first hostname
ordering (`S<site>_<role><idx>`).

### sid mapping for the current 16 switches

| Switch  | old sid | new sid | Switch  | old sid | new sid |
|---------|---------|---------|---------|---------|---------|
| S1_BG1  | 31      | 1301    | S3_BG1  | 33      | 3301    |
| S1_SP1  | 41      | 1401    | S3_SP1  | 43      | 3401    |
| S1_LE1  | 51      | 1501    | S3_LE1  | 55      | 3501    |
| S1_LE2  | 52      | 1502    | S4_BG1  | 34      | 4301    |
| S1_TOR1 | 61      | 1601    | S4_SP1  | 44      | 4401    |
| S2_BG1  | 32      | 2301    | S4_LE1  | 57      | 4501    |
| S2_SP1  | 42      | 2401    | S4_LE2  | 58      | 4502    |
| S2_LE1  | 53      | 2501    | S4_LE3  | 59      | 4503    |

The new scheme also regularizes leaf numbering: today leaf index is a global counter
(S2_LE1=53, S3_LE1=55, S4_LE1=57); under `SRII` each site's first leaf is `S501`.

## Design

### 1. MAC scheme

Split `sid` into two halves and place them in the outer octets, freeing the middle octet for
the per-interface discriminator:

```
52:54:00 : [sid_hi] : [iface] : [sid_lo]
            octet4     octet5    octet6
```

```python
sid_hi, sid_lo = divmod(sid, 100)   # sid_hi = site·role (0–99), sid_lo = index (0–99)

# mgmt:        f"{base_mac}:{sid_hi:02x}:00:{sid_lo:02x}"
# ethernet i:  f"{base_mac}:{sid_hi:02x}:{port:02x}:{sid_lo:02x}"
```

- `octet4` = `sid // 100` (= site·role, e.g. 13 → `0x0d`).
- `octet5` = interface byte: `0x00` for mgmt, the port number `1..N` for each ethernet ISL.
- `octet6` = `sid % 100` (= index, e.g. `01`).

**Uniqueness.** `(sid_hi, sid_lo)` is a bijection of the full sid, so it is distinct per
switch. `octet5` is distinct per interface within a switch. Ethernet ports start at 1, so they
never collide with mgmt's `0x00`. Both halves are `0–99` (≤ `0x63`), safely inside one octet.

This is a deliberate change from the old layout (where `octet5` was a mgmt/eth *type* flag and
`octet6` held the port): the per-interface index consolidates into `octet5`, and `octet6` is
repurposed to carry the low half of the sid.

### 2. Port scheme

Replace string concatenation with an additive offset:

```python
telnet_port  = 10000 + sid    # range 11301 … 14503
monitor_port = 20000 + sid    # range 21301 … 24503
```

- Both bands sit entirely below 32768, clear of Linux's default ephemeral range
  (32768–60999), so a transient outbound socket cannot steal the listen port before QEMU binds.
- The two bands are 10000 apart and never overlap; telnet and monitor for the same sid always
  differ by exactly 10000.
- A 4-digit sid (max 9999) guarantees both ports stay ≤ 65535.
- Fully reversible: `sid = telnet_port − 10000`.

These are centralized as two read-only `@property` methods on `SwitchConfig`
(`telnet_port`, `monitor_port`), and the four scattered `"90{sid:02d}"` / `"44{sid:02d}"`
string-concats are replaced with references to them. This removes the duplication rather than
editing four copies.

### 3. Validation

`SwitchConfig.__post_init__` changes its range check from `1 ≤ sid ≤ 255` to
`1000 ≤ sid ≤ 9999`, with the error message updated to match. This enforces 4 digits — which is
exactly what keeps both MAC halves in-octet and both ports legal.

Validation stays a **plain numeric range**. It deliberately does *not* hard-code role semantics
(e.g. rejecting `role ∉ {3,4,5,6}`), to keep the generator decoupled from role conventions.

### 4. `con_*` console helpers

Each helper's hard-coded telnet port is recomputed as `10000 + sid`:

| Helper       | old   | new   | Helper      | old   | new   |
|--------------|-------|-------|-------------|-------|-------|
| con_s1_bg1   | 9031  | 11301 | con_s2_bg1  | 9032  | 12301 |
| con_s1_sp1   | 9041  | 11401 | con_s2_sp1  | 9042  | 12401 |
| con_s1_le1   | 9051  | 11501 | con_s2_le1  | 9053  | 12501 |
| con_s1_le2   | 9052  | 11502 | con_s3_le1  | 9055  | 13501 |
| con_s1_tor1  | 9061  | 11601 | con_s4_le1  | 9057  | 14501 |

(The `ssh_*` helpers are unaffected — they use mgmt IPs assigned by NX-OS config, independent
of sid.)

## Out of scope

- **`ssh_*` helpers / mgmt-IP last-octet convention** — hand-maintained, not generated by the
  script, only loosely coupled to sid.
- **`config/ansible/dynamic_inventory.py` MAC defaults** (`0000.00SS.000N`) — a separate
  convention with a different OUI/format; not generated here.

## Known side effect (not avoidable, flagged)

The SMBIOS serial is `f"00000000{sid}"`, so it naturally lengthens (`...0031` → `...1301`).
The pattern is left untouched. Because the serial is the switch's identity in NDFC, renumbering
means the n9kvs present new serials and any already-registered switches would re-discover. This
is inherent to renumbering the lab, not something the code change can prevent.

## Files touched

- `config/nexus9000v/nexus9000v_new.py` — validation range, `StandardMACGenerator` (both
  methods), `SwitchConfig` port properties, and the four port call-sites.
- `config/nexus9000v/S*_*.yaml` (16 files) — new `sid` values per the mapping table.
- `config/nexus9000v/con_s*` (10 files) — new telnet ports.

## Verification

No test suite exists (per `CLAUDE.md`). Validate with:

- `mypy config/nexus9000v/nexus9000v_new.py`
- `flake8 config/nexus9000v/nexus9000v_new.py` (169-char line length)
- `python3 nexus9000v_new.py --config S1_LE1.yaml --dry-run` for a representative switch, and
  confirm the printed MACs and telnet/monitor ports match the mapping above.
- Spot-check that the dry-run MACs across two switches sharing a (site, role) — e.g. S1_LE1
  (1501) and S1_LE2 (1502) — differ only in `octet6`.
