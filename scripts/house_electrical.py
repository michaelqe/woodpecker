"""Electrical fixtures in the house model: sockets, switches, lights, outlets, thermostats.

Magpie: House > Digital Twin (HOUSE-2) and House > Electricity (circuit schedule).
Source: the four 2006 wiring drawings 050607TP (Starget Grupp OÜ, 06.06.07, 1:50), photographed
7 Nov 2026 and attached to the House > Electricity page:
  EX-01 ground-floor sockets (I korruse elektriseadmed)   EE-01 ground-floor lighting (I korruse valgustus)
  EX-02 upper-floor sockets (II korruse elektriseadmed)   EE-02 upper-floor lighting (II korruse valgustus)

Positions were read off the photos and mapped into the model's drawing coordinates (the same x/y
as house_model.py) with a perspective fit to the room corners; the fit is good to about 250 mm.
fixture_parts() then puts each wall item on the nearest real wall face (or the fireplace) on the
side of its room, clear of doors and windows, and each ceiling item inside its room. So x/y below
are approximate; the room, the wall and the height are what count. Nothing here was checked on site,
and the drawings are from 2006: the house may have changed since.

Heights are the drawing's: sockets 300 mm above the floor unless the label says otherwise
(e.g. "9P1/1,1" = 1100). Switches 900, thermostats 1500 and wall lights as given are assumed.

FIXTURES row: (id, floor, room, kind, x, y, height above floor or None, circuit, sheet, label, note)
room "OUT" = on the outside of an exterior wall. circuit = schedule row on House > Electricity
(the drawings' group numbers match the schedule rows); None = low-current or not on the drawing.
"""

GROUND, UPPER = 0, 1

# Schedule rows used by the drawings (House > Electricity). Kept short; the page has the breakers.
CIRCUITS = {
    2: "Sauna heater (elektrikeris), 25 A",
    5: "Kitchen microwave socket (crossed out on the schedule; check)",
    6: "Kitchen socket, amended schedule entry (check)",
    7: "Dishwasher",
    8: "Fridge",
    9: "Kitchen sockets",
    11: "Ground-floor sockets: kitchen, living room, veranda, hall",
    12: "Ground- and upper-floor sockets: bedrooms 1-4, stairs",
    13: "Computer sockets: office, bedrooms 2-4",
    14: "Gas hob electric ignition",
    15: "Lighting: hall and kitchen",
    16: "Lighting: living room, office, stairwell",
    17: "Lighting: bedrooms (and kitchen hood)",
    21: "Gas boiler",
    22: "Underfloor heating manifolds (thermostat cables 4x0.75 go to the manifold)",
    26: "Washing machine",
    27: "Bathroom sockets",
    28: "Outdoor sockets",
    30: "Upper-floor whirlpool bath",
    31: "Lighting: WC, sink room, plant room, bathrooms",
    32: "External gates",
    33: "External lighting",
    34: "Twilight switch (HL) lighting",
}
LOW_CURRENT = "Low-current outlet: UTP 4x2x0.5 Cat 5 or RG 6, to the low-current panel; no mains circuit."

# kind: (description, material, width along the wall, height, depth off the wall, mount)
# mount: wall | ceiling | floor (supply: wall unless height is None = ceiling, or 0 = floor)
KINDS = {
    "socket": ("Socket, earthed, flush", "socket", 80, 80, 25, "wall"),
    "socket-ip44": ("Socket, earthed, with lid (IP44)", "socket", 85, 85, 40, "wall"),
    "data": ("Phone + data outlet", "data", 80, 80, 25, "wall"),
    "phone": ("Phone outlet", "data", 80, 80, 25, "wall"),
    "antenna": ("TV antenna outlet", "data", 80, 80, 25, "wall"),
    "thermostat": ("Underfloor heating thermostat", "thermostat", 85, 85, 25, "wall"),
    "switch": ("Light switch, flush", "switch", 80, 80, 15, "wall"),
    "sensor": ("Twilight switch sensor", "switch", 70, 70, 50, "wall"),
    "supply": ("Supply point (cable left for an appliance or light)", "supply", 100, 100, 30, "wall"),
    "panel": ("Distribution board", "panel", 500, 700, 120, "wall"),
    "light-ceiling": ("Ceiling light (IP20)", "light", 300, 80, 300, "ceiling"),
    "light-ceiling-ip44": ("Ceiling light (IP44)", "light", 220, 80, 220, "ceiling"),
    "light-recessed": ("Recessed ceiling downlight", "light", 100, 15, 100, "ceiling"),
    "light-spot": ("Surface-mounted directional spotlight", "light", 120, 100, 120, "ceiling"),
    "light-wall": ("Wall light", "light", 200, 200, 100, "wall"),
    "light-outdoor": ("Outdoor wall light (IP55)", "light", 200, 250, 120, "wall"),
    "light-cornice": ("Strip light behind the cornice (IP44)", "light", 1200, 60, 60, "wall"),
    "light-sauna": ("Sauna light, wall (IP55)", "light", 200, 200, 100, "wall"),
}

MATERIALS = {
    "socket": {"name": "Socket (reference)", "kind": "reference", "color": "#f3efe6"},
    "switch": {"name": "Switch or sensor (reference)", "kind": "reference", "color": "#9fb0bb"},
    "light": {"name": "Light fitting (reference)", "kind": "reference", "color": "#f2c94c"},
    "data": {"name": "Low-current outlet (reference)", "kind": "reference", "color": "#6fa8dc"},
    "thermostat": {"name": "Thermostat (reference)", "kind": "reference", "color": "#c27ba0"},
    "supply": {"name": "Supply point (reference)", "kind": "reference", "color": "#e07b39"},
    "panel": {"name": "Distribution board (reference)", "kind": "reference", "color": "#6d7378"},
}

FIXTURES = [
    ("el-g01", GROUND, "kook", "socket", 7970, 580, 1000, 5, "EX-01", "5P", ""),
    ("el-g02", GROUND, "kook", "socket", 7970, 830, 1500, 6, "EX-01", "6P", ""),
    ("el-g03", GROUND, "kook", "supply", 7970, 700, 1500, None, "EX-01", "Under-cabinet lighting supply", ""),
    ("el-g04", GROUND, "kook", "socket", 8010, 2330, 200, 7, "EX-01", "7P", ""),
    ("el-g05", GROUND, "kook", "socket", 7940, 2960, 1100, 9, "EX-01", "9P4", "Moved clear of the kitchen window; the drawing has it about 300 mm closer."),
    ("el-g06", GROUND, "kook", "socket", 7940, 3190, 1100, 9, "EX-01", "9P5", "Moved clear of the kitchen window; the drawing has it about 300 mm closer."),
    ("el-g07", GROUND, "kook", "socket", 7950, 3420, 1100, 9, "EX-01", "9P6", "Moved clear of the kitchen window; the drawing has it about 300 mm closer."),
    ("el-g08", GROUND, "kook", "socket", 8080, 3460, 200, 8, "EX-01", "8P", ""),
    ("el-g09", GROUND, "kook", "socket", 6110, 430, 1100, 9, "EX-01", "9P3", ""),
    ("el-g10", GROUND, "kook", "socket", 5870, 420, 1100, 9, "EX-01", "9P2", ""),
    ("el-g11", GROUND, "kook", "socket", 5650, 420, 1100, 9, "EX-01", "9P1", ""),
    ("el-g12", GROUND, "kook", "supply", 5770, 850, 0, 14, "EX-01", "Gas hob supply from the floor", ""),
    ("el-g13", GROUND, "kook", "supply", 6040, 870, None, 17, "EX-01", "Cooker hood supply from the ceiling", ""),
    ("el-g14", GROUND, "kook", "socket", 4730, 310, 300, 11, "EX-01", "11P9", ""),
    ("el-g15", GROUND, "stair-floor", "socket", 5790, 4170, 300, 11, "EX-01", "11P10", ""),
    ("el-g16", GROUND, "kook", "thermostat", 5890, 3710, 1500, 22, "EX-01", "Thermostat 3", ""),
    ("el-g17", GROUND, "esik", "thermostat", 4790, 6070, 1500, 22, "EX-01", "Thermostat 4", ""),
    ("el-g18", GROUND, "elutuba", "thermostat", 2130, 9560, 1500, 22, "EX-01", "Thermostat 1", ""),
    ("el-g19", GROUND, "kabinet", "thermostat", 4100, 10240, 1500, 22, "EX-01", "Thermostat 2", ""),
    ("el-g20", GROUND, "kook", "antenna", 3670, 370, 300, None, "EX-01", "TV outlet", ""),
    ("el-g21", GROUND, "kook", "socket", 3330, 360, 300, 11, "EX-01", "11P8", ""),
    ("el-g22", GROUND, "kook", "socket", 3140, 360, 300, 11, "EX-01", "11P7", ""),
    ("el-g23", GROUND, "kook", "socket", 3690, 3780, 300, 11, "EX-01", "11P6", ""),
    ("el-g24", GROUND, "terrass", "socket-ip44", 2400, 470, 300, 11, "EX-01", "11P (veranda)", ""),
    ("el-g25", GROUND, "elutuba", "antenna", 2870, 4110, 300, None, "EX-01", "TV outlet", ""),
    ("el-g26", GROUND, "elutuba", "phone", 2680, 4120, 300, None, "EX-01", "Phone outlet", ""),
    ("el-g27", GROUND, "elutuba", "socket", 2400, 4110, 300, 11, "EX-01", "11P5", ""),
    ("el-g28", GROUND, "elutuba", "socket", 2150, 4090, 300, 11, "EX-01", "11P4", ""),
    ("el-g29", GROUND, "elutuba", "socket", 1930, 4100, 300, 11, "EX-01", "11P3", ""),
    ("el-g30", GROUND, "elutuba", "socket", 340, 9600, 300, 11, "EX-01", "11P2", ""),
    ("el-g31", GROUND, "esik", "socket", 5740, 9850, 300, 11, "EX-01", "11P1", ""),
    ("el-g32", GROUND, "pesuruum", "socket-ip44", 7320, 10140, 300, 27, "EX-01", "27P1", ""),
    ("el-g33", GROUND, "tehnoruum", "supply", 7910, 12220, 1500, 21, "EX-01", "Gas boiler supply", ""),
    ("el-g34", GROUND, "tehnoruum", "supply", 7930, 13540, 1500, 22, "EX-01", "Underfloor heating manifold supply", ""),
    ("el-g35", GROUND, "OUT", "supply", 8210, 14450, 300, 32, "EX-01", "External gates supply", ""),
    ("el-g36", GROUND, "OUT", "socket-ip44", 7990, 14660, 300, 28, "EX-01", "Outdoor socket", ""),
    ("el-g37", GROUND, "tehnoruum", "socket-ip44", 6000, 13970, 300, 26, "EX-01", "26P (washing machine)", ""),
    ("el-g38", GROUND, "kabinet", "socket", 4400, 10110, 300, 12, "EX-01", "12P1", ""),
    ("el-g39", GROUND, "kabinet", "socket", 3130, 13300, 300, 13, "EX-01", "13P1", ""),
    ("el-g40", GROUND, "kabinet", "socket", 3140, 13550, 300, 13, "EX-01", "13P2", ""),
    ("el-g41", GROUND, "kabinet", "socket", 3140, 13800, 300, 13, "EX-01", "13P3", ""),
    ("el-g42", GROUND, "kabinet", "data", 3130, 14000, 300, None, "EX-01", "Phone + data outlet", ""),
    ("el-g43", GROUND, "tehnoruum", "panel", 5970, 12150, 1500, None, "EX-01", "PJK main distribution board", ""),
    ("el-u01", UPPER, "mag1", "socket", 6770, 350, 300, 12, "EX-02", "12P8", ""),
    ("el-u02", UPPER, "mag1", "socket", 4520, 350, 300, 12, "EX-02", "12P7", ""),
    ("el-u03", UPPER, "mag1", "socket", 5710, 3830, 300, 12, "EX-02", "12P9", ""),
    ("el-u04", UPPER, "trepihall", "socket", 6910, 6480, 300, 12, "EX-02", "12P10", ""),
    ("el-u05", UPPER, "mag2", "socket", 3670, 4170, 300, 12, "EX-02", "12P6", ""),
    ("el-u06", UPPER, "mag2", "socket", 4400, 5710, 300, 12, "EX-02", "12P5", ""),
    ("el-u07", UPPER, "mag3", "socket", 3610, 7110, 300, 12, "EX-02", "12P4", ""),
    ("el-u08", UPPER, "mag3", "socket", 4520, 8700, 300, 12, "EX-02", "12P3", ""),
    ("el-u09", UPPER, "mag4", "socket", 4640, 9990, 300, 12, "EX-02", "12P2", ""),
    ("el-u10", UPPER, "vann1", "socket-ip44", 7880, 7950, 1600, 27, "EX-02", "27P2", ""),
    ("el-u11", UPPER, "vann1", "socket-ip44", 7830, 9770, 1600, 27, "EX-02", "27P3", ""),
    ("el-u12", UPPER, "vann2", "supply", 8060, 11620, 300, 30, "EX-02", "Whirlpool bath supply", ""),
    ("el-u13", UPPER, "leil", "supply", 6780, 13940, 300, 2, "EX-02", "Sauna heater supply (elektrikeris)", ""),
    ("el-u14", UPPER, "vann1", "thermostat", 6140, 9560, 1500, 22, "EX-02", "Thermostat 5", ""),
    ("el-u15", UPPER, "mag4", "socket", 3150, 11980, 300, 13, "EX-02", "13P6", ""),
    ("el-u16", UPPER, "mag4", "socket", 3160, 12220, 300, 13, "EX-02", "13P5", ""),
    ("el-u17", UPPER, "mag4", "socket", 3160, 12470, 300, 13, "EX-02", "13P4", ""),
    ("el-u18", UPPER, "mag4", "data", 3130, 12690, 300, None, "EX-02", "Phone + data outlet", ""),
    ("el-u19", UPPER, "mag4", "antenna", 3140, 12910, 300, None, "EX-02", "TV outlet", ""),
    ("el-u20", UPPER, "mag2", "socket", 370, 5900, 300, 13, "EX-02", "13P12", ""),
    ("el-u21", UPPER, "mag2", "socket", 380, 6150, 300, 13, "EX-02", "13P11", ""),
    ("el-u22", UPPER, "mag2", "socket", 380, 6380, 300, 13, "EX-02", "13P10", ""),
    ("el-u23", UPPER, "mag2", "data", 380, 6600, 300, None, "EX-02", "Phone + data outlet", ""),
    ("el-u24", UPPER, "mag2", "antenna", 380, 6820, 300, None, "EX-02", "TV outlet", ""),
    ("el-u25", UPPER, "mag3", "socket", 620, 8830, 300, 13, "EX-02", "13P9", ""),
    ("el-u26", UPPER, "mag3", "socket", 620, 9040, 300, 13, "EX-02", "13P8", ""),
    ("el-u27", UPPER, "mag3", "socket", 620, 9230, 300, 13, "EX-02", "13P7", ""),
    ("el-u28", UPPER, "mag3", "thermostat", 450, 9220, 1500, 22, "EX-02", "Thermostat with floor sensor", ""),
    ("el-u29", UPPER, "mag3", "data", 420, 9420, 300, None, "EX-02", "Phone + data outlet", ""),
    ("el-u30", UPPER, "mag3", "antenna", 430, 9660, 300, None, "EX-02", "TV outlet", ""),
    ("el-g44", GROUND, "kook", "light-recessed", 7010, 1200, None, 15, "EE-01", "Kitchen downlight (switch 3)", ""),
    ("el-g45", GROUND, "kook", "light-recessed", 6930, 2270, None, 15, "EE-01", "Kitchen downlight (switch 3)", ""),
    ("el-g46", GROUND, "kook", "light-recessed", 6980, 3220, None, 15, "EE-01", "Kitchen downlight (switch 3)", ""),
    ("el-g47", GROUND, "kook", "light-recessed", 5920, 2250, None, 15, "EE-01", "Kitchen downlight (switch 4)", ""),
    ("el-g48", GROUND, "kook", "light-recessed", 5960, 3210, None, 15, "EE-01", "Kitchen downlight (switch 4)", ""),
    ("el-g49", GROUND, "kook", "light-ceiling", 4200, 2050, None, 15, "EE-01", "Kitchen table light (switch 5)", ""),
    ("el-g50", GROUND, "kook", "switch", 5710, 3740, 900, 15, "EE-01", "Switches 3-4-5 (kitchen lights)", ""),
    ("el-g51", GROUND, "stair-floor", "switch", 5700, 4220, 900, 15, "EE-01", "Switches 1-2 (hall lights)", ""),
    ("el-g52", GROUND, "stair-floor", "switch", 5710, 4410, 900, 16, "EE-01", "Two-way switch (stair light, with the upper floor)", ""),
    ("el-g53", GROUND, "esik", "light-spot", 5220, 4820, None, 15, "EE-01", "Hall spotlight (switch 2)", ""),
    ("el-g54", GROUND, "esik", "light-spot", 5240, 6040, None, 15, "EE-01", "Hall spotlight (switch 2)", ""),
    ("el-g55", GROUND, "esik", "light-spot", 5380, 7270, None, 15, "EE-01", "Hall spotlight (switch 2)", ""),
    ("el-g56", GROUND, "esik", "light-spot", 5330, 8410, None, 15, "EE-01", "Hall spotlight (switch 2)", ""),
    ("el-g57", GROUND, "esik", "light-ceiling-ip44", 7890, 7320, None, 15, "EE-01", "Entrance light (switch 1)", ""),
    ("el-g58", GROUND, "esik", "light-ceiling-ip44", 6630, 7290, None, 15, "EE-01", "Entrance light (switch 1)", ""),
    ("el-g59", GROUND, "esik", "switch", 8120, 6540, 900, 15, "EE-01", "Switches 1-2 by the front door", ""),
    ("el-g60", GROUND, "OUT", "light-outdoor", 8780, 6360, 1800, 33, "EE-01", "Front door wall light", ""),
    ("el-g61", GROUND, "OUT", "light-outdoor", 8510, 440, 2500, 33, "EE-01", "House number light", ""),
    ("el-g62", GROUND, "OUT", "supply", 8610, 5750, 2200, 33, "EE-01", "Outdoor light supply (provision)", ""),
    ("el-g63", GROUND, "OUT", "supply", 2650, 320, 2200, 33, "EE-01", "Outdoor light supply (provision)", ""),
    ("el-g64", GROUND, "OUT", "supply", 8020, 14450, 2200, 33, "EE-01", "Outdoor light supply (provision)", ""),
    ("el-g65", GROUND, "OUT", "sensor", 9170, 8190, 2500, 34, "EE-01", "Twilight switch sensor (HL)", ""),
    ("el-g66", GROUND, "esik", "light-wall", 4940, 7270, 1600, 16, "EE-01", "Wall light with its own switch", ""),
    ("el-g67", GROUND, "esik", "switch", 4490, 5890, 900, 16, "EE-01", "Switches 1-2 (living room lights)", ""),
    ("el-g68", GROUND, "elutuba", "light-ceiling", 2020, 5850, None, 16, "EE-01", "Living room ceiling light", ""),
    ("el-g69", GROUND, "elutuba", "light-ceiling", 2080, 8120, None, 16, "EE-01", "Living room ceiling light", ""),
    ("el-g70", GROUND, "terrass", "light-ceiling", 1510, 1080, None, None, "EE-01", "Veranda ceiling light", ""),
    ("el-g71", GROUND, "terrass", "light-ceiling", 1480, 2680, None, None, "EE-01", "Veranda ceiling light", ""),
    ("el-g72", GROUND, "kook", "switch", 3020, 3530, 900, None, "EE-01", "Switch (veranda lights)", ""),
    ("el-g73", GROUND, "esik", "switch", 4480, 8480, 900, 16, "EE-01", "Switches 1-2 (living room lights)", ""),
    ("el-g74", GROUND, "kabinet", "switch", 4570, 9940, 900, 16, "EE-01", "Two-way switch (office light, with bedroom 4 upstairs)", ""),
    ("el-g75", GROUND, "kabinet", "light-ceiling", 4330, 11180, None, 16, "EE-01", "Office ceiling light", ""),
    ("el-g76", GROUND, "kabinet", "light-ceiling", 4370, 12810, None, 16, "EE-01", "Office ceiling light", ""),
    ("el-g77", GROUND, "wc0", "light-ceiling-ip44", 6960, 9260, None, 31, "EE-01", "WC ceiling light", ""),
    ("el-g78", GROUND, "pesuruum", "light-ceiling-ip44", 6860, 10440, None, 31, "EE-01", "Sink room ceiling light", ""),
    ("el-g79", GROUND, "pesuruum", "light-ceiling-ip44", 6830, 11430, None, 31, "EE-01", "Sink room ceiling light", ""),
    ("el-g80", GROUND, "esik", "switch", 6200, 9620, 900, 31, "EE-01", "Switches 1-2 (WC and sink room)", ""),
    ("el-g81", GROUND, "wc0", "supply", 7310, 9990, 2500, 31, "EE-01", "Mirror light supply", ""),
    ("el-g82", GROUND, "tehnoruum", "light-ceiling", 6880, 13060, None, 31, "EE-01", "Plant room ceiling light", ""),
    ("el-g83", GROUND, "tehnoruum", "switch", 7150, 12290, 900, 31, "EE-01", "Switches 1-2 (plant room)", ""),
    ("el-u31", UPPER, "mag1", "light-spot", 6970, 930, None, 17, "EE-02", "Bedroom 1 spotlight", ""),
    ("el-u32", UPPER, "mag1", "light-spot", 7020, 1940, None, 17, "EE-02", "Bedroom 1 spotlight", ""),
    ("el-u33", UPPER, "mag1", "light-spot", 7060, 2970, None, 17, "EE-02", "Bedroom 1 spotlight", ""),
    ("el-u34", UPPER, "mag1", "light-ceiling", 5190, 1850, None, 17, "EE-02", "Bedroom 1 ceiling light (switch 1)", ""),
    ("el-u35", UPPER, "mag1", "light-wall", 6140, 320, 1500, 17, "EE-02", "Bedside wall light", ""),
    ("el-u36", UPPER, "mag1", "light-wall", 5130, 250, 1500, 17, "EE-02", "Bedside wall light", ""),
    ("el-u37", UPPER, "mag1", "switch", 5600, 300, 900, 17, "EE-02", "Bedside switches 1-2", ""),
    ("el-u38", UPPER, "mag1", "switch", 5660, 3320, 900, 17, "EE-02", "Switches 1-2 (bedroom 1)", ""),
    ("el-u39", UPPER, "mag1", "switch", 3140, 3400, 900, 34, "EE-02", "Switch (balcony light)", ""),
    ("el-u40", UPPER, "OUT", "light-outdoor", 2660, 2730, 2200, 34, "EE-02", "Balcony light", ""),
    ("el-u41", UPPER, "stairwell", "light-ceiling-ip44", 7490, 5260, None, 16, "EE-02", "Stairwell light", ""),
    ("el-u42", UPPER, "stairwell", "light-ceiling-ip44", 6320, 5190, None, 16, "EE-02", "Stairwell light", ""),
    ("el-u43", UPPER, "trepihall", "light-ceiling-ip44", 5140, 5150, None, 16, "EE-02", "Stairwell light", ""),
    ("el-u44", UPPER, "trepihall", "switch", 5490, 4390, 900, 16, "EE-02", "Two-way switches (stair, with the ground floor)", ""),
    ("el-u45", UPPER, "trepihall", "light-ceiling", 6590, 6870, None, 16, "EE-02", "Landing ceiling light", ""),
    ("el-u46", UPPER, "trepihall", "light-ceiling", 5350, 6880, None, 16, "EE-02", "Landing ceiling light", ""),
    ("el-u47", UPPER, "trepihall", "light-ceiling", 5420, 8820, None, 16, "EE-02", "Landing ceiling light", ""),
    ("el-u48", UPPER, "wc1", "light-ceiling-ip44", 7690, 7220, None, 31, "EE-02", "WC ceiling light", ""),
    ("el-u49", UPPER, "wc1", "light-wall", 7600, 7660, 1800, 31, "EE-02", "WC wall light with its own switch", ""),
    ("el-u50", UPPER, "trepihall", "switch", 7000, 6770, 900, 31, "EE-02", "Switch (WC light)", ""),
    ("el-u51", UPPER, "vann1", "light-ceiling-ip44", 7710, 8440, None, 31, "EE-02", "Bathroom ceiling light (switch 1)", ""),
    ("el-u52", UPPER, "vann1", "light-ceiling-ip44", 7810, 9540, None, 31, "EE-02", "Bathroom ceiling light (switch 1)", ""),
    ("el-u53", UPPER, "vann1", "light-ceiling-ip44", 6670, 8400, None, 31, "EE-02", "Bathroom ceiling light (switch 1)", ""),
    ("el-u54", UPPER, "vann1", "light-ceiling-ip44", 6790, 9500, None, 31, "EE-02", "Bathroom ceiling light (switch 1)", ""),
    ("el-u55", UPPER, "vann1", "light-cornice", 8540, 9440, 2300, 31, "EE-02", "Cornice light (switch 4)", ""),
    ("el-u56", UPPER, "vann2", "light-ceiling-ip44", 7950, 10810, None, 31, "EE-02", "Bathroom ceiling light (switch 2)", ""),
    ("el-u57", UPPER, "vann2", "light-ceiling-ip44", 7620, 11610, None, 31, "EE-02", "Bathroom ceiling light (switch 2)", ""),
    ("el-u58", UPPER, "vann2", "light-ceiling-ip44", 6860, 10760, None, 31, "EE-02", "Bathroom ceiling light (switch 2)", ""),
    ("el-u59", UPPER, "vann2", "light-cornice", 8540, 11370, 2300, 31, "EE-02", "Cornice light (switch 5)", ""),
    ("el-u60", UPPER, "leil", "light-sauna", 7820, 12300, 1800, 31, "EE-02", "Sauna light (switch 3)", ""),
    ("el-u61", UPPER, "leil", "light-sauna", 7680, 13960, 1800, 31, "EE-02", "Sauna light (switch 3)", ""),
    ("el-u62", UPPER, "trepihall", "switch", 5890, 8940, 900, 31, "EE-02", "Switches 1-5 (bathroom, sauna)", ""),
    ("el-u63", UPPER, "mag2", "switch", 4430, 5710, 900, 17, "EE-02", "Switch (bedroom 2)", ""),
    ("el-u64", UPPER, "mag2", "light-ceiling", 3390, 5390, None, 17, "EE-02", "Bedroom 2 ceiling light", ""),
    ("el-u65", UPPER, "mag2", "light-ceiling", 1420, 5330, None, 17, "EE-02", "Bedroom 2 ceiling light", ""),
    ("el-u66", UPPER, "mag3", "switch", 4560, 8800, 900, 17, "EE-02", "Switch (bedroom 3)", ""),
    ("el-u67", UPPER, "mag3", "light-ceiling", 3530, 8440, None, 17, "EE-02", "Bedroom 3 ceiling light", ""),
    ("el-u68", UPPER, "mag3", "light-ceiling", 1460, 8380, None, 17, "EE-02", "Bedroom 3 ceiling light", ""),
    ("el-u69", UPPER, "mag4", "switch", 4960, 10230, 900, 17, "EE-02", "Switch (bedroom 4)", ""),
    ("el-u70", UPPER, "mag4", "switch", 5000, 9880, 900, 16, "EE-02", "Two-way switch (office light downstairs)", ""),
    ("el-u71", UPPER, "mag4", "light-ceiling", 4580, 11130, None, 17, "EE-02", "Bedroom 4 ceiling light", ""),
    ("el-u72", UPPER, "mag4", "light-ceiling", 4300, 12980, None, 17, "EE-02", "Bedroom 4 ceiling light", ""),
]

CEILING = 2700        # above the floor, both storeys (assumed, as in house_model.py)
GROUND_FLOOR_TOP = 20  # ground-floor finish is 20 mm thick in the model
SNAP_RANGE = 1500     # a wall item further than this from any usable wall face is an error
SNAPPABLE_BLOCKS = ("fireplace", "hall-wardrobe", "chimney-up")


def _inside(rects, x, y):
    return any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in rects)


def _faces(walls, blocks, floor):
    """Wall faces on a floor: (axis, coord, sign, lo, hi, exterior, openings)."""
    out = []
    for _, f, _, (x0, y0, x1, y1), openings in walls:
        if f != floor:
            continue
        along_x = (x1 - x0) >= (y1 - y0)
        exterior = ((y1 - y0) if along_x else (x1 - x0)) >= 280
        out += [("x", x0, -1, y0, y1, exterior, [] if along_x else openings),
                ("x", x1, +1, y0, y1, exterior, [] if along_x else openings),
                ("y", y0, -1, x0, x1, exterior, openings if along_x else []),
                ("y", y1, +1, x0, x1, exterior, openings if along_x else [])]
    for bid, f, _, (x0, y0, x1, y1), *_ in blocks:
        if f == floor and bid in SNAPPABLE_BLOCKS:
            out += [("x", x0, -1, y0, y1, False, []), ("x", x1, +1, y0, y1, False, []),
                    ("y", y0, -1, x0, x1, False, []), ("y", y1, +1, x0, x1, False, [])]
    return out


def _clear_of_openings(along, w, z0, z1, openings, lo, hi):
    """Slide a wall item along its wall until it no longer covers a door or window."""
    from_sill = {"w": 900, "d": 0, "o": 0}
    for o in sorted(openings, key=lambda o: o["a"]):
        sill = o.get("sill", from_sill[o["t"]])
        head = o.get("head", 2100)
        if z1 <= sill or z0 >= head or along + w / 2 <= o["a"] or along - w / 2 >= o["b"]:
            continue
        left, right = o["a"] - w / 2 - 50, o["b"] + w / 2 + 50
        left_ok, right_ok = left - w / 2 >= lo, right + w / 2 <= hi
        if left_ok and (not right_ok or along - left <= right - along):
            along = left
        elif right_ok:
            along = right
    return along


def _wall_spot(fx, faces, rooms_here, room_rects, x, y, w, z0, z1):
    best = None
    for axis, c, sign, lo, hi, exterior, openings in faces:
        if hi - lo < w + 20:
            continue
        along = min(max(y if axis == "x" else x, lo + w / 2 + 10), hi - w / 2 - 10)
        along = _clear_of_openings(along, w, z0, z1, openings, lo, hi)
        qx, qy = (c + sign * 100, along) if axis == "x" else (along, c + sign * 100)
        if fx[2] == "OUT":
            if not exterior or _inside(rooms_here, qx, qy):
                continue
        elif not _inside(room_rects, qx, qy):
            continue
        px, py = (c, along) if axis == "x" else (along, c)
        d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        if best is None or d < best[0]:
            best = (d, axis, c, sign, along)
    if best is None or best[0] > SNAP_RANGE:
        raise ValueError(f"{fx[0]} ({fx[9]}): no wall face of {fx[2]} near {x}, {y}")
    return best[1:]


def placed(walls, blocks, rooms, level):
    """Each fixture with its box in drawing coordinates: (fixture, x0, y0, z0, x1, y1, z1)."""
    room_rects = {r[0]: r[5] for r in rooms}
    room_rects["stairwell"] = [[5773, 4034, 8166, 6234]]  # open stairwell upstairs, not a traced room
    indoor = {f: [rc for r in rooms if r[1] == f and r[6] != "outside" for rc in r[5]] for f in level}
    faces = {f: _faces(walls, blocks, f) for f in level}
    out = []
    for fx in FIXTURES:
        fid, f, room, kind, x, y, h = fx[:7]
        _, _, w, hh, d, mount = KINDS[kind]
        base = level[f]["z"] + (GROUND_FLOOR_TOP if f == GROUND else 0)
        if kind == "supply" and h is None:
            mount = "ceiling"
        elif kind == "supply" and h == 0:
            mount = "floor"
        if mount == "wall":
            z0 = base + h - hh / 2
            axis, c, sign, along = _wall_spot(fx, faces[f], indoor[f], room_rects.get(room, []), x, y, w, z0, z0 + hh)
            a0, a1 = along - w / 2, along + w / 2
            n0, n1 = sorted((c, c + sign * d))
            box = (n0, a0, n1, a1) if axis == "x" else (a0, n0, a1, n1)
            out.append((fx, box[0], box[1], z0, box[2], box[3], z0 + hh))
            continue
        rect = min(room_rects[room], key=lambda r: max(r[0] - x, 0, x - r[2]) + max(r[1] - y, 0, y - r[3]))
        m = w / 2 + 50
        cx = min(max(x, rect[0] + m), rect[2] - m)
        cy = min(max(y, rect[1] + m), rect[3] - m)
        if mount == "floor":
            z0, z1 = base, base + 30
        else:
            z1 = level[f]["z"] + CEILING
            z0 = z1 - hh
        out.append((fx, cx - w / 2, cy - d / 2, z0, cx + w / 2, cy + d / 2, z1))
    return out


def fixture_parts(walls, blocks, rooms, level, box):
    parts = []
    for fx, x0, y0, z0, x1, y1, z1 in placed(walls, blocks, rooms, level):
        fid, f, room, kind, _, _, h, circuit, sheet, label, note = fx
        desc = KINDS[kind][0]
        where = "outside" if room == "OUT" else next((r[3] for r in rooms if r[0] == room), "stairwell")
        if circuit is None:
            circ = LOW_CURRENT if kind in ("data", "phone", "antenna") else "Circuit not shown on the drawing (check)."
        else:
            circ = f"Circuit: schedule row {circuit}, {CIRCUITS[circuit]}."
        height = "" if h is None else f" Centre {h} mm above the floor." if h else " At floor level."
        role = f"{desc}: {label} ({where.lower()}). {circ}{height} From drawing {sheet} (2006)."
        notes = "Position read off the 2006 wiring drawing, about 250 mm. " + note
        group = "Electrical, outside" if room == "OUT" else f"Electrical, {level[f]['name'].lower()}"
        parts.append(box(fid, f"{label} ({desc.split(',')[0].split(' (')[0].lower()})", group,
                         KINDS[kind][1], x0, y0, z0, x1, y1, z1, role, notes.strip()))
    return parts


def fixture_report():
    """Counts per room and per circuit, for the ticket and the Magpie page."""
    from collections import Counter
    by_room = Counter((fx[1], fx[2], fx[3].split("-")[0]) for fx in FIXTURES)
    by_circuit = Counter(fx[7] for fx in FIXTURES)
    return by_room, by_circuit
