from typing import TYPE_CHECKING
import logging
from ... import TransactionKind
from .comgate_lib import Comgate, CurrencyCodes, CountryCodes
from ..utils import get_supported_currencies
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ...interface import GatewayConfig, GatewayResponse, PaymentData, \
    InitializedPaymentResponse

logger = logging.getLogger(__name__)

GATEWAY_NAME = "Comgate.cz"


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class ComgateGatewayPlugin(BasePlugin):
    PLUGIN_NAME = GATEWAY_NAME
    PLUGIN_ID = "anezka.payments.comgate"
    DEFAULT_CONFIGURATION = [
        {"name": "Merchant", "value": None},
        {"name": "Secret API key", "value": None},
        {"name": "Permitted payment methods", "value": "ALL"},
        {"name": "Currency", "value": "EUR"},
        {"name": "Country", "value": "SK"},
        {"name": "Test Mode", "value": False},
    ]

    CONFIG_STRUCTURE = {
        "Merchant": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "E-shop identifier in the ComGate system - you can find it in the Client Portal in the section e-shop settings - e-shop connection.",
            "label": "Merchant ID",
        },
        "Secret API key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Password for the backgorund comunication with the ComGate system - you can find it in the Client Portal in the section e-shop settings - e-shop connection - connection detail.",
            "label": "Secret API key",
        },
        "Permitted payment methods": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "The method of payment from the table of payment methods, the value \"ALL\" if the method is to be chosen by the payer, or a simple expression with the choice of methods (described by the link below)."
                         "https://help.comgate.cz/docs/cs/api-protokol#v%C3%BDb%C4%9Br-platebn%C3%AD-metody",
            "https://help.comgate.cz/docs/protocol-api-en#code-lists"
            "label": "Permitted payment methods",
        },
        "Currency": {
            "type": ConfigurationTypeField.STRING,
            "help_text": 'Currency code according to ISO 4217. Available currencies: CZK, EUR, PLN, HUF, USD, GBP, RON, HRK, NOK, SEK.',
            "label": "Currency",
        },
        "Country": {
            "type": ConfigurationTypeField.STRING,
            "help_text": 'Possible values: ALL, AT, BE, CY, CZ, DE, EE, EL, ES, FI, FR, GB, HR, HU, IE, IT, LT, LU, LV, MT, NL, NO, PL, PT, RO, SL, SK, SV, US. If the parameter is missing, "CZ" is used automatically. The parameter is used to limit the selection of payment methods at the payment gateway. It is necessary to select the correct combination of "country" and "curr" parameters for the given region. For example, to display Czech buttons and pay by card in CZK, choose the combination country = CZ and curr = CZK. For Slovak bank buttons and card payments in EUR, select country = SK and curr = EUR. For Polish bank buttons and card payment in PLN, select country = PL and curr = PLN. For other foreign currencies, you can use the country = ALL parameter or another country code that the payment gateway accepts.',
            "label": "Country",
        },
        "Test Mode": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": '⚠️ DANGEROUSE ⚠️ If set to true all the payment will be completed without charging of money. Never enable in production!',
            "label": "Test mode",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=False,
            supported_currencies=configuration["Currency"],
            connection_params={
                "merchant": configuration["Merchant"],
                "secret": configuration["Secret API key"],
                "test": configuration["Test Mode"],
                "country": configuration["Country"],
                "currency": configuration["Currency"],
                "payment_methods": configuration["Permitted payment methods"],
            },
            store_customer=False,
        )

    def get_comgate_client(self):
        config = self._get_gateway_config()

        return Comgate(
            merchant=config.connection_params['merchant'],
            secret=config.connection_params['secret'],
            test=config.connection_params['test']
        )

    def _get_gateway_config(self):
        return self.config

    @require_active_plugin
    def process_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        config = self._get_gateway_config()

        gate = self.get_comgate_client()

        is_success = False
        error_msg = None

        (transId, redirect) = None, None
        try:
            (transId, redirect) = gate.create(
                country=CountryCodes[config.connection_params['country']],
                price=int(payment_information.amount * 100),
                currency=CurrencyCodes[payment_information.currency],
                label=f"Order ID {payment_information.order_id}",
                refId=str(payment_information.order_id),
                method=config.connection_params['payment_methods'],
                email=payment_information.customer_email,
                prepareOnly=True,
            )
            is_success = True
        except Exception as e:
            logger.exception(e)
            error_msg = "Payment gateway error (Create request failed)"

        return GatewayResponse(
            is_success=is_success,
            kind=TransactionKind.PENDING,
            amount=payment_information.amount,
            currency=payment_information.currency,
            customer_id=payment_information.customer_id,
            transaction_id=transId,
            error=error_msg,
            payment_method_info=None,
            action_required=False,
            raw_response={
                'transId': transId,
                'redirect': redirect,
            },
        )

    @require_active_plugin
    def initialize_payment(
            self, payment_data, previous_value
    ) -> "InitializedPaymentResponse":
        return InitializedPaymentResponse(
            gateway=self.PLUGIN_ID, name=self.PLUGIN_NAME, data=payment_data | {
                'TRANSACTION_ID': '123abc'
            }
        )

    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

    @require_active_plugin
    def get_payment_config(self, previous_value):
        config = self._get_gateway_config()
        return [
            {
                "field": "ola",
                "value": 'Hello there 👋',
            }
        ]
