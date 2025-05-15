import importlib

from django.conf import settings
from payroll.apps import PayrollConfig


class PaymentGatewayConfig:
    """
    Configuration handler for payment gateway integrations.
    Supports payment point specific configurations with fallback to global settings.
    """
    def __init__(self, payment_point=None):
        # Load gateway configuration based on payment point if provided
        gateway_config = self._get_gateway_config(payment_point)
        
        self.gateway_base_url = gateway_config.get('gateway_base_url', PayrollConfig.gateway_base_url)
        self.endpoint_payment = gateway_config.get('endpoint_payment', PayrollConfig.endpoint_payment)
        self.endpoint_reconciliation = gateway_config.get('endpoint_reconciliation', PayrollConfig.endpoint_reconciliation)
        self.auth_type = gateway_config.get('payment_gateway_auth_type', PayrollConfig.payment_gateway_auth_type)
        self.api_key = gateway_config.get('payment_gateway_api_key', PayrollConfig.payment_gateway_api_key)
        self.basic_auth_username = gateway_config.get('payment_gateway_basic_auth_username', PayrollConfig.payment_gateway_basic_auth_username)
        self.basic_auth_password = gateway_config.get('payment_gateway_basic_auth_password', PayrollConfig.payment_gateway_basic_auth_password)
        self.timeout = gateway_config.get('payment_gateway_timeout', PayrollConfig.payment_gateway_timeout)
        
        # Payment gateway connector implementation class
        self.payment_gateway_class = gateway_config.get('payment_gateway_class', PayrollConfig.payment_gateway_class)

    def _get_gateway_config(self, payment_point):
        """
        Retrieve the gateway configuration for a specific payment point.
        """
        if not payment_point:
            return {}
        
        payment_gateways = getattr(settings, 'PAYMENT_GATEWAYS', {})
        return payment_gateways.get(payment_point.name, {})

    def get_headers(self):
        if self.auth_type == 'token':
            return {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
        elif self.auth_type == 'basic':
            import base64
            auth_str = f"{self.basic_auth_username}:{self.basic_auth_password}"
            auth_bytes = auth_str.encode('utf-8')
            auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
            return {
                'Authorization': f'Basic {auth_base64}',
                'Content-Type': 'application/json',
            }
        else:
            return {
                'Content-Type': 'application/json',
            }

    def get_payment_gateway_connector(self):
        module_name, class_name = self.payment_gateway_class.rsplit('.', 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def get_payment_endpoint(self):
        return self.endpoint_payment

    def get_reconciliation_endpoint(self):
        return self.endpoint_reconciliation
