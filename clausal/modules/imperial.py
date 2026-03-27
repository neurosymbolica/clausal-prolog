"""clausal.modules.imperial — Imperial and non-SI unit vectors.

All values are plain ``Quantity`` objects stored in SI base units.  Use them
by multiplying a scalar in a ``++()`` escape::

    -import_from(py.imperial, [inch, foot, pound_mass, mph, lbf])

    LEN  := ++(20 * inch)           # Quantity(0.508,   {Metre: 1})
    MASS := ++(150 * pound_mass)    # Quantity(68.04,   {Kilogram: 1})
    SPD  := ++(60 * mph)            # Quantity(26.82,   {Metre:1, Second:-1})

Because dimensions are identical to their SI equivalents, ``has_units`` checks
work without any changes::

    has_units(++(20 * inch), Metre)   # succeeds — both have {Metre: 1}
"""

from clausal.terms import Quantity
from clausal.modules.units import (
    Metre, Kilogram, Second, Kelvin,
)

# ═════════════════════════════════════════════════════════════════════════════
# Length  (stored as metres)
# ═════════════════════════════════════════════════════════════════════════════

inch              = Quantity(0.0254,              {Metre: 1})
foot              = Quantity(0.3048,              {Metre: 1})
yard              = Quantity(0.9144,              {Metre: 1})
mile              = Quantity(1_609.344,           {Metre: 1})
nautical_mile     = Quantity(1_852.0,             {Metre: 1})
light_year        = Quantity(9.4607304725808e15,  {Metre: 1})
astronomical_unit = Quantity(1.495978707e11,      {Metre: 1})

# ═════════════════════════════════════════════════════════════════════════════
# Mass  (stored as kilograms)
# ═════════════════════════════════════════════════════════════════════════════

pound_mass        = Quantity(0.45359237,          {Kilogram: 1})
ounce_mass        = Quantity(0.028349523125,      {Kilogram: 1})
stone             = Quantity(6.35029318,          {Kilogram: 1})
short_ton         = Quantity(907.18474,           {Kilogram: 1})
long_ton          = Quantity(1_016.0469088,       {Kilogram: 1})

# ═════════════════════════════════════════════════════════════════════════════
# Force  (stored as Newtons = kg·m/s²)
# ═════════════════════════════════════════════════════════════════════════════

pound_force       = Quantity(4.4482216152605,     {Kilogram: 1, Metre: 1, Second: -2})

# ═════════════════════════════════════════════════════════════════════════════
# Volume  (stored as cubic metres)
# ═════════════════════════════════════════════════════════════════════════════

litre             = Quantity(1e-3,                {Metre: 3})
millilitre        = Quantity(1e-6,                {Metre: 3})
gallon_us         = Quantity(3.785411784e-3,      {Metre: 3})
quart_us          = Quantity(9.46352946e-4,       {Metre: 3})
pint_us           = Quantity(4.73176473e-4,       {Metre: 3})
fluid_ounce_us    = Quantity(2.95735295625e-5,    {Metre: 3})
gallon_uk         = Quantity(4.54609e-3,          {Metre: 3})
pint_uk           = Quantity(5.6826125e-4,        {Metre: 3})
fluid_ounce_uk    = Quantity(2.84130625e-5,       {Metre: 3})

# ═════════════════════════════════════════════════════════════════════════════
# Pressure  (stored as Pascals = kg/(m·s²))
# ═════════════════════════════════════════════════════════════════════════════

psi               = Quantity(6_894.757,           {Kilogram: 1, Metre: -1, Second: -2})

# ═════════════════════════════════════════════════════════════════════════════
# Energy  (stored as Joules = kg·m²/s²)
# ═════════════════════════════════════════════════════════════════════════════

calorie           = Quantity(4.184,               {Kilogram: 1, Metre: 2, Second: -2})
kilocalorie       = Quantity(4_184.0,             {Kilogram: 1, Metre: 2, Second: -2})
btu               = Quantity(1_055.05585262,      {Kilogram: 1, Metre: 2, Second: -2})
kilowatt_hour     = Quantity(3_600_000.0,         {Kilogram: 1, Metre: 2, Second: -2})

# ═════════════════════════════════════════════════════════════════════════════
# Power  (stored as Watts = kg·m²/s³)
# ═════════════════════════════════════════════════════════════════════════════

horsepower        = Quantity(745.69987,           {Kilogram: 1, Metre: 2, Second: -3})

# ═════════════════════════════════════════════════════════════════════════════
# Speed  (stored as m/s)
# ═════════════════════════════════════════════════════════════════════════════

mph               = Quantity(0.44704,             {Metre: 1, Second: -1})   # miles per hour
kph               = Quantity(1.0 / 3.6,           {Metre: 1, Second: -1})   # kilometres per hour
knot              = Quantity(1_852.0 / 3_600.0,   {Metre: 1, Second: -1})   # nautical mile/h

# ═════════════════════════════════════════════════════════════════════════════
# Temperature differences  (ratio-scale only, stored as Kelvin)
# ═════════════════════════════════════════════════════════════════════════════
# Absolute offset scales (Celsius, Fahrenheit) are unsupported.

rankine           = Quantity(5.0 / 9.0,           {Kelvin: 1})              # °R → K

# ═════════════════════════════════════════════════════════════════════════════
# Abbreviations  (import explicitly)
# ═════════════════════════════════════════════════════════════════════════════

ft   = foot
yd   = yard
mi   = mile
nmi  = nautical_mile
ly   = light_year
au   = astronomical_unit

lb   = pound_mass
lbm  = pound_mass   # explicit mass disambiguation
oz   = ounce_mass

lbf  = pound_force

l    = litre        # lowercase L; standard SI symbol
ml   = millilitre
