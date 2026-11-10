from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union, Optional, Dict
from sqlalchemy.orm import Session

@dataclass(frozen=True)
class CurrencySpec:
    code: str
    symbol: str
    precision: int  # number of minor decimal digits (e.g. 2 for GBP, 0 for JPY, 3 for KWD)
    name: str

# Centralized ISO 4217 Currency Specification Registry
SUPPORTED_CURRENCIES: Dict[str, CurrencySpec] = {
    # 2-decimal currencies (valid as base ledger or foreign transaction origin)
    "GBP": CurrencySpec("GBP", "£", 2, "British Pound"),
    "USD": CurrencySpec("USD", "$", 2, "US Dollar"),
    "EUR": CurrencySpec("EUR", "€", 2, "Euro"),
    "CAD": CurrencySpec("CAD", "CA$", 2, "Canadian Dollar"),
    "AUD": CurrencySpec("AUD", "A$", 2, "Australian Dollar"),
    "CHF": CurrencySpec("CHF", "CHF", 2, "Swiss Franc"),
    "NZD": CurrencySpec("NZD", "NZ$", 2, "New Zealand Dollar"),
    "SGD": CurrencySpec("SGD", "SG$", 2, "Singapore Dollar"),
    "HKD": CurrencySpec("HKD", "HK$", 2, "Hong Kong Dollar"),
    "INR": CurrencySpec("INR", "₹", 2, "Indian Rupee"),
    "SEK": CurrencySpec("SEK", "kr", 2, "Swedish Krona"),
    "NOK": CurrencySpec("NOK", "kr", 2, "Norwegian Krone"),
    "DKK": CurrencySpec("DKK", "kr", 2, "Danish Krone"),
    "PLN": CurrencySpec("PLN", "zł", 2, "Polish Zloty"),
    "ZAR": CurrencySpec("ZAR", "R", 2, "South African Rand"),
    
    # 0-decimal currencies (valid as foreign transaction origin only)
    "JPY": CurrencySpec("JPY", "¥", 0, "Japanese Yen"),
    "KRW": CurrencySpec("KRW", "₩", 0, "South Korean Won"),
    "CLP": CurrencySpec("CLP", "CLP$", 0, "Chilean Peso"),
    "VND": CurrencySpec("VND", "₫", 0, "Vietnamese Dong"),
    "ISK": CurrencySpec("ISK", "kr", 0, "Icelandic Króna"),
    
    # 3-decimal currencies (valid as foreign transaction origin only)
    "KWD": CurrencySpec("KWD", "KWD", 3, "Kuwaiti Dinar"),
    "BHD": CurrencySpec("BHD", "BHD", 3, "Bahraini Dinar"),
    "OMR": CurrencySpec("OMR", "OMR", 3, "Omani Rial"),
    "JOD": CurrencySpec("JOD", "JOD", 3, "Jordanian Dinar"),
    "TND": CurrencySpec("TND", "TND", 3, "Tunisian Dinar"),
}

BASE_CURRENCY_SETTING_KEY = "base_currency"
DEFAULT_BASE_CURRENCY = "GBP"

def get_currency_spec(code: str) -> CurrencySpec:
    """Returns CurrencySpec for currency code, or a fallback 2-decimal spec if unknown."""
    clean = (code or "GBP").strip().upper()
    if clean in SUPPORTED_CURRENCIES:
        return SUPPORTED_CURRENCIES[clean]
    return CurrencySpec(code=clean, symbol=clean, precision=2, name=clean)

def get_stored_base_currency(db: Session) -> Optional[str]:
    """Retrieves the stored base currency from system_settings, or None if not initialized."""
    from app.models import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.key == BASE_CURRENCY_SETTING_KEY).first()
    return setting.value.strip().upper() if setting and setting.value else None


def get_base_currency_readonly(db: Session) -> str:
    """Reads configured base currency without writing to system_settings if unset."""
    import os
    stored = get_stored_base_currency(db)
    if stored:
        return stored
    env_base = os.getenv("BASE_CURRENCY")
    if env_base and env_base.strip():
        return env_base.strip().upper()
    return DEFAULT_BASE_CURRENCY

def get_effective_base_currency(db: Session) -> str:
    """
    Authoritative base currency resolution with startup safety rules:
    1. If a stored base currency exists in database, it is authoritative.
       If environment variable BASE_CURRENCY is explicitly set and conflicts, fail fast.
       If BASE_CURRENCY is unset or empty, use stored value without conflict.
    2. If no stored base currency exists (first-run initialization):
       Consult environment variable BASE_CURRENCY (defaults to 'GBP').
       Enforce that base currency has 2-decimal minor unit precision.
       Persist to system_settings and return it.
    """
    import os
    env_base = os.getenv("BASE_CURRENCY")
    env_base_clean = env_base.strip().upper() if env_base and env_base.strip() else None

    stored = get_stored_base_currency(db)
    if stored:
        if env_base_clean and env_base_clean != stored:
            raise RuntimeError(
                f"Base currency configuration conflict! "
                f"Stored base currency in database is '{stored}', but environment variable BASE_CURRENCY is '{env_base_clean}'. "
                f"To prevent reinterpreting existing financial amounts, the application will not start. "
                f"Either unset BASE_CURRENCY or restore it to '{stored}'."
            )
        return stored

    # First-run initialization
    target_currency = env_base_clean or DEFAULT_BASE_CURRENCY
    spec = SUPPORTED_CURRENCIES.get(target_currency)
    if not spec:
        raise ValueError(f"Unsupported base currency '{target_currency}'. Currency must be in supported registry.")
    if spec.precision != 2:
        raise ValueError(
            f"Unsupported base currency '{target_currency}' (minor unit precision: {spec.precision}). "
            f"The base ledger requires a 2-decimal minor unit precision (scale factor 100, e.g. GBP, EUR, USD, CAD, AUD, CHF)."
        )

    from app.models import SystemSetting
    new_setting = SystemSetting(key=BASE_CURRENCY_SETTING_KEY, value=target_currency)
    db.add(new_setting)
    db.commit()
    return target_currency

def get_base_currency_spec(db: Session) -> CurrencySpec:
    """Returns the CurrencySpec for the active installation base currency."""
    base_code = get_effective_base_currency(db)
    return get_currency_spec(base_code)

def validate_origin_amount(amount: Union[Decimal, float, int, str], currency_code: str) -> Decimal:
    """
    Validates that a foreign transaction amount conforms to the currency's ISO 4217 minor unit precision.
    Returns the parsed Decimal.
    """
    spec = get_currency_spec(currency_code)
    try:
        raw_str = str(amount).strip().replace(spec.symbol, "").replace(",", "")
        d = Decimal(raw_str)
    except (InvalidOperation, TypeError):
        raise ValueError(f"Invalid monetary amount: '{amount}'.")

    if d <= 0:
        raise ValueError("Transaction amount must be strictly greater than zero.")

    # Validate decimal places against currency precision
    exp = abs(d.as_tuple().exponent) if d.as_tuple().exponent < 0 else 0
    if exp > spec.precision:
        raise ValueError(
            f"Amount '{d}' has {exp} decimal places, but currency '{spec.code}' supports at most {spec.precision} decimals."
        )
    return d

def format_origin_amount(amount: Union[Decimal, float, int, str], currency_code: str) -> str:
    """Formats amount with native currency symbol and precision (e.g. ¥1,500, $42.50, KWD 5.250)."""
    spec = get_currency_spec(currency_code)
    d = Decimal(str(amount))
    if spec.precision == 0:
        num_str = f"{int(d):,}"
    else:
        fmt = f"{{:,.{spec.precision}f}}"
        num_str = fmt.format(d)
    sep = " " if len(spec.symbol) > 1 else ""
    return f"{spec.symbol}{sep}{num_str}"

# --- Canonical Base-Ledger Minor Unit Conversions (Scale Factor 100) ---

def major_to_minor_units(val: Union[float, str, int, Decimal]) -> int:
    """
    Safely converts a base-currency major unit value (e.g. 19.99) to integer minor units (scale 100).
    Avoids binary floating-point drift using Decimal with ROUND_HALF_UP:
    e.g. 19.99 -> 1999 minor units.
    """
    if isinstance(val, (int, str)):
        cleaned = str(val).strip()
        for sym in ["£", "$", "€", "₹", "CA$", "A$", "SG$", "NZ$", "zł", "R", "kr", "CHF"]:
            cleaned = cleaned.replace(sym, "")
        cleaned = cleaned.replace(",", "")
        d = Decimal(cleaned)
    elif isinstance(val, float):
        d = Decimal(str(val))
    elif isinstance(val, Decimal):
        d = val
    else:
        raise TypeError(f"Cannot convert type {type(val)} to minor units")

    return int((d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def minor_to_major_units(minor: int) -> float:
    """Converts integer minor units to float major units for API serialization."""
    return float(Decimal(minor) / Decimal(100))

def format_base_amount(minor: int, currency_symbol: str = "£") -> str:
    """
    Formats integer minor units into standard major currency string:
    e.g. 1450 -> '£14.50', -250 -> '-£2.50'
    """
    major = Decimal(minor) / Decimal(100)
    sep = " " if (len(currency_symbol) > 1 and currency_symbol[-1].isalpha()) else ""
    if minor < 0:
        return f"-{currency_symbol}{sep}{abs(major):,.2f}"
    return f"{currency_symbol}{sep}{major:,.2f}"


def get_excel_currency_number_format(currency_code: str) -> str:
    """
    Returns an Excel-compatible number format string for the given ISO 4217 currency code,
    using the currency's configured symbol, spacing, and decimal precision.
    Examples:
      GBP -> '"£"#,##0.00;-"£"#,##0.00;"£"0.00'
      USD -> '"$"#,##0.00;-"$"#,##0.00;"$"0.00'
      EUR -> '"€"#,##0.00;-"€"#,##0.00;"€"0.00'
      CHF -> '"CHF "#,##0.00;-"CHF "#,##0.00;"CHF "0.00'
      INR -> '"₹"#,##0.00;-"₹"#,##0.00;"₹"0.00'
    """
    spec = get_currency_spec(currency_code)
    sym = spec.symbol
    sep = " " if (len(sym) > 1 and sym[-1].isalpha()) else ""
    dec_zeros = ("." + ("0" * spec.precision)) if spec.precision > 0 else ""
    quoted_sym = f'"{sym}{sep}"'
    return f"{quoted_sym}#,##0{dec_zeros};-{quoted_sym}#,##0{dec_zeros};{quoted_sym}0{dec_zeros}"

# Backward-compatibility aliases for existing calls
pounds_to_pence = major_to_minor_units
pence_to_pounds = minor_to_major_units
format_pence = format_base_amount

def format_unit_price(amount: Union[Decimal, float, int, str], currency_symbol: str = "£") -> str:
    """
    Formats unit price preserving up to 4 decimal places in major currency units.
    Displays minimum 2 decimal places, extending up to 4 decimal places for fractional pence.
    Examples:
      12.3456 -> '£12.3456'
      12.3400 -> '£12.34'
      12.5000 -> '£12.50'
      12.3450 -> '£12.345'
    """
    d = Decimal(str(amount)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    formatted = f"{d:,.4f}"
    parts = formatted.split(".")
    integer_part = parts[0]
    decimal_part = parts[1]
    trimmed_decimal = decimal_part.rstrip("0")
    if len(trimmed_decimal) < 2:
        trimmed_decimal = decimal_part[:2]
    sep = " " if len(currency_symbol) > 1 else ""
    return f"{currency_symbol}{sep}{integer_part}.{trimmed_decimal}"

