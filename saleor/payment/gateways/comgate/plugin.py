import codecs
import decimal
import json
import urllib.parse
from json import JSONDecodeError
from pprint import pprint
from typing import TYPE_CHECKING, Optional, Any
import logging

from saleor.order.actions import order_captured
from saleor.order.events import external_notification_event
from ...utils import create_transaction, TransactionKind, create_payment_information, \
    gateway_postprocess

from django.core.exceptions import ObjectDoesNotExist
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseBadRequest

from saleor.checkout.models import Checkout
from saleor.order.models import Order
from ... import TransactionKind, PaymentError
from .comgate_lib import Comgate, CurrencyCodes, CountryCodes
from ..utils import get_supported_currencies
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ...interface import GatewayConfig, GatewayResponse, PaymentData, \
    InitializedPaymentResponse
from ...models import Payment

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

    def get_checkout(self, payment: Payment) -> Optional[Checkout]:
        if not payment.checkout:
            return None
        # Lock checkout in the same way as in checkoutComplete
        return (
            Checkout.objects.select_for_update(of=("self",))
                .prefetch_related("gift_cards", "lines__variant__product", )
                .select_related("shipping_method__shipping_zone")
                .filter(pk=payment.checkout.pk)
                .first()
        )

    @require_active_plugin
    def process_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return GatewayResponse(
            is_success=True,
            action_required=False,
            kind=TransactionKind.PENDING,
            amount=payment_information.amount,
            currency=payment_information.currency,
            error=None,
            transaction_id=payment_information.token,
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

    # TODO: This should only run is COMGATE gateway is used
    @require_active_plugin
    def order_created(self, order: "Order", previous_value: Any):
        config = self._get_gateway_config()

        gate = self.get_comgate_client()


        (transId, redirect) = None, None
        try:
            (transId, redirect) = gate.create(
                country=CountryCodes[config.connection_params['country']],
                price=int(order.total_net.amount * 100),
                currency=CurrencyCodes[order.currency],
                label=f"Order ID {order.id}",
                refId=str(order.token),
                method=config.connection_params['payment_methods'],
                email=order.user_email,
                prepareOnly=True,
            )
        except Exception as e:
            logger.exception(e)
            error_msg = "Payment gateway error (Create request failed)"

        try:
            order.store_value_in_metadata(
                items={'COMGATE_PAYMENT_URL': redirect})
            order.save()

        except ObjectDoesNotExist:
            raise PaymentError(
                "Payment cannot be performed. Order does not exists.")

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

    @require_active_plugin
    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        config = self._get_gateway_config()
        if not path.startswith('/webhook/status'):
            return HttpResponseNotFound()

        try:
            response_data = urllib.parse.parse_qs(codecs.decode(request.body))
        except:
            logger.warning("Cannot parse request body.")
            return HttpResponse("[accepted]")


        merchant = response_data['merchant'][0]
        # test = response_data['test'][0]
        price = decimal.Decimal(response_data['price'][0]) / 100
        curr = response_data['curr'][0]
        # label = response_data['label'][0]
        refId = response_data['refId'][0]
        # method = response_data['method'][0]
        # email = response_data['email'][0]
        # phone = response_data['phone'][0]
        transId = response_data['transId'][0]
        secret = response_data['secret'][0]
        status = response_data['status'][0]

        if secret != config.connection_params['secret']:
            return HttpResponseBadRequest("Invalid secret")
        if merchant != config.connection_params['merchant']:
            return HttpResponseBadRequest("Merchant do not match")

        token = refId

        order = Order.objects.filter(token=token).first()

        if order is None or order.token != refId:
            logger.warning("Order not found")
            return HttpResponseBadRequest("Order not found")

        payment = Payment.objects.get(order_id=order.id)

        # 'PaymentData'
        payment_information = create_payment_information(
            payment=payment,
            payment_token=token,
            amount=price,
        )

        if status == "PAID":
            kind = TransactionKind.CAPTURE
        elif status == "CANCELED":
            kind = TransactionKind.CANCEL
        else:
            return HttpResponse()

        gateway_response = GatewayResponse(
            is_success=True,
            action_required=False,
            kind=kind,
            amount=price,
            currency=curr,
            transaction_id=transId,
            error=None,
            # raw_response={"request": request.body},
            searchable_key=transId,
        )

        transaction = create_transaction(
            payment=payment,
            kind=kind,
            payment_information=payment_information,
            gateway_response=gateway_response
        )

        gateway_postprocess(transaction, payment)
        order_captured(payment.order, None, transaction.amount, payment)
        external_notification_event(
            order=payment.order,
            user=None,
            message="Comgate payment request  was successful.",
            parameters={"service": payment.gateway, "id": payment.token},
        )

        # print("payment")
        # pprint(payment)
        # print("payment_information")
        # pprint(payment_information)
        # print("gateway_response")
        # pprint(gateway_response)
        # print("Transaction")
        # pprint(transaction)

        return HttpResponse()
