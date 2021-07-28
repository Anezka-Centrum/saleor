import codecs
import logging
import urllib.parse
from enum import Enum
from typing import NamedTuple
from urllib.parse import urljoin

import requests

from .utils import prepare_params

logger = logging.getLogger(__name__)

COMGATE_API = 'https://payments.comgate.cz/v1.0/'


class CountryCodes(Enum):
    ALL = "ALL"
    AT = "AT"
    BE = "BE"
    CY = "CY"
    CZ = "CZ"
    DE = "DE"
    EE = "EE"
    EL = "EL"
    ES = "ES"
    FI = "FI"
    FR = "FR"
    GB = "GB"
    HR = "HR"
    HU = "HU"
    IE = "IE"
    IT = "IT"
    LT = "LT"
    LU = "LU"
    LV = "LV"
    MT = "MT"
    NL = "NL"
    NO = "NO"
    PL = "PL"
    PT = "PT"
    RO = "RO"
    SL = "SL"
    SK = "SK"
    SV = "SV"
    US = "US"


class CurrencyCodes(Enum):
    CZK = "CZK"
    EUR = "EUR"
    PLN = "PLN"
    HUF = "HUF"
    USD = "USD"
    GBP = "GBP"
    RON = "RON"
    HRK = "HRK"
    NOK = "NOK"
    SEK = "SEK"


class LangCodes(Enum):
    CS = "cs"
    SK = "sk"
    EN = "en"
    PL = "pl"
    FR = "fr"
    RO = "ro"
    DE = "de"
    HU = "hu"
    SI = "si"
    HR = "hr"


TransactionCreateErrorCodes = dict([
    (1100, "neznámá chyba"),
    (1102, "zadaný jazyk není podporován"),
    (1103, "nesprávně zadaná metoda"),
    (1104, "nelze načíst platbu"),
    (1107, "cena platby není podporovaná"),
    (1200, "databázová chyba"),
    (1301, "neznámý e-shop"),
    (1303, "propojení nebo jazyk chybí"),
    (1304, "neplatná kategorie"),
    (1305, "chybí popis produktu"),
    (1306, "vyberte správnou metodu"),
    (1308, "vybraný způsob platby není povolen"),
    (1309, "nesprávná částka"),
    (1310, "neznámá měna"),
    (1311, "neplatný identifikátor bankovního účtu Klienta"),
    (1316, "e-shop nemá povolené opakované platby"),
    (1317, "neplatná metoda – nepodporuje opakované platby"),
    (1319, "nelze založit platbu, problém na straně banky"),
    (1399, "neočekávaný výsledek z databáze"),
    (1400, "chybný dotaz"),
    (1500, "neočekávaná chyba"),
])


class TransactionCreateError(Exception):

    def __init__(self, errorCode: int):
        self.code = errorCode
        self.message = TransactionCreateErrorCodes.get(errorCode)
        super().__init__(self.message)

class Comgate:
    def __init__(self, merchant: str, secret: str, test: bool):
        self.merchant = merchant
        self.secret = secret
        self.test = test

    CreateResponse = NamedTuple('CreateResponse', [('transId', str), ('redirect', str)])

    def create(self,
               country: Enum,
               price: int,
               currency: Enum,
               label: str,
               refId: str,
               method: str,
               email: str,
               prepareOnly: bool,
               phone: str = None,
               account: str = None,
               productName: str = None,
               lang: Enum = None,
               preauth: bool = None,
               initRecurring: bool = None,
               verification: bool = None,
               eetReport: bool = None,
               eetData: bool = None,
               embedded: bool = None,
               ) -> CreateResponse:
        if not isinstance(country, CountryCodes):
            raise TypeError('Country must be an instance of CountryCodes')

        if not isinstance(currency, CurrencyCodes):
            raise TypeError('Currency must be an instance of CurrencyCodes')

        if lang is not None and not isinstance(lang, LangCodes):
            raise TypeError('Currency must be an instance of LangCodes')

        if (prepareOnly is not True):
            raise ValueError(
                'prepareOnly must be True for creating transactions from backend')

        params = {
            "merchant": self.merchant,
            "test": self.test,
            "country": country.value,
            "price": price,
            "curr": currency.value,
            "label": label,
            "refId": refId,
            "method": method,
            "account": account,
            "email": email,
            "phone": phone,
            "name": productName,
            "lang": None if lang is None else lang.value,
            "prepareOnly": prepareOnly,
            "secret": self.secret,
            "preauth": preauth,
            "initRecurring": initRecurring,
            "verification": initRecurring,
            "eetReport": initRecurring,
            "eetData": initRecurring,
            "embedded": initRecurring,
        }

        logger.info('Creating new payment using Comgate payment gateway...')

        try:
            response = requests.post(
                urljoin(COMGATE_API, 'create'),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=prepare_params(params),
                # allow_redirects=False,
            )

            print("response.content", codecs.decode(response.content))
            print("content", urllib.parse.parse_qs(codecs.decode(response.content)))

            response.raise_for_status()

            content = urllib.parse.parse_qs(codecs.decode(response.content))
            code = int(content['code'][0])
            message = content['message'][0]
            transId = content['transId'][0]
            redirect = content['redirect'][0]

            if code != 0:
                logger.error(
                    'Payment gateway responded with code %d amd message %s(%s)' % (
                        code, message, TransactionCreateErrorCodes[code]))

                raise RuntimeError(
                    'Payment gateway responded with code %d amd message %s(%s)' % (
                        code, message, TransactionCreateErrorCodes[code]))

            logger.info('Comgate payment successfully created!')

            return self.CreateResponse(transId, redirect)
        except:
            logger.error('Error while making request to Comgate payment gateway!')

            raise RuntimeError('Error while making request to Comgate payment gateway')
