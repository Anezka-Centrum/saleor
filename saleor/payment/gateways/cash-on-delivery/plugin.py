import logging

from django.core.exceptions import ObjectDoesNotExist

from saleor.order.models import Order
from saleor.plugins.base_plugin import BasePlugin
from ..utils import get_supported_currencies
from ... import TransactionKind, PaymentError
from ...interface import GatewayConfig, GatewayResponse, PaymentData

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
    PLUGIN_ID = "anezka.payments.cashOnDelivery"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=False,
            supported_currencies=configuration["Currency"],
            connection_params={},
            store_customer=False,
        )

    def _get_gateway_config(self):
        return self.config

    @require_active_plugin
    def process_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        order = Order.objects.filter(id=payment_information.order_id).first()

        try:
            order.store_value_in_metadata(
                items={'CASH_ON_DELIVERY': 'YES'})
            order.save()
        except ObjectDoesNotExist:
            raise PaymentError(
                "Payment cannot be performed. Order does not exists.")

        return GatewayResponse(
            is_success=True,
            action_required=False,
            kind=TransactionKind.CAPTURE,
            amount=payment_information.amount,
            currency=payment_information.currency,
            error=None,
            transaction_id=payment_information.token,
        )


    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

