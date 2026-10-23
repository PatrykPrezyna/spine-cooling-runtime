# Medical Device Prototype V1

```mermaid
gantt
    title Cool Spine (Animal Study Ready)
    dateFormat YYYY-MM-DD
    axisFormat %d-%b

    Cooling System V0        :cool0, 2026-10-20, 21d
    Cooling System V1 Aspen  :cool1, 2026-10-27, 28d
    Cartridge V2             :cart, 2026-10-20, 21d
    Housing V1               :house, 2026-10-20, 28d
    New Electronic Board     :elec, 2026-10-20, 14d
    Battery & UPS            :ups, 2026-10-27, 14d
    Build Prototype V1       :crit, build, after ready, 14d
    Final Verification       :crit, verify, after build, 7d

    Animal Study             :milestone, 2027-02-01, 0d
```