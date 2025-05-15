import unittest
from unittest.mock import patch, MagicMock, call
from django.test import TestCase, override_settings

from payroll.strategies.strategy_online_payment import StrategyOnlinePayment
from payroll.payment_gateway.payment_gateway_connector import PaymentGatewayConnector
from payroll.tests.helpers import PaymentPointHelper


# Custom payment gateway connector for testing
class CustomPaymentGatewayConnector(PaymentGatewayConnector):
    def send_payment(self, invoice_id, amount, **kwargs):
        return {"status": "success", "payment_id": "custom-123"}

    def reconcile(self, invoice_id, amount, **kwargs):
        return {"status": "reconciled", "payment_id": "custom-123"}


# Default payment gateway connector for testing
class DefaultPaymentGatewayConnector(PaymentGatewayConnector):
    def send_payment(self, invoice_id, amount, **kwargs):
        return {"status": "success", "payment_id": "default-123"}

    def reconcile(self, invoice_id, amount, **kwargs):
        return {"status": "reconciled", "payment_id": "default-123"}


class TestStrategyOnlinePayment(TestCase):
    CUSTOM_PAYMENT_GATEWAYS = {
        'testPaymentPoint1': {
            'gateway_base_url': 'https://custom-gateway.com/api/',
            'endpoint_payment': '/payments',
            'endpoint_reconciliation': '/reconcile',
            'payment_gateway_auth_type': 'token',
            'payment_gateway_api_key': 'custom-api-key',
            'payment_gateway_timeout': 30,
            'payment_gateway_class': 'payroll.tests.strategy_online_payment_tests.CustomPaymentGatewayConnector'
        }
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        StrategyOnlinePayment.PAYMENT_GATEWAY = None
        cls.payment_point_helper = PaymentPointHelper()
        cls.mock_custom_payment_point = cls.payment_point_helper.get_or_create_payment_point_api()
        cls.mock_custom_payment_point.name = 'testPaymentPoint1'

    def setUp(self):
        StrategyOnlinePayment.PAYMENT_GATEWAY = None

    @patch('payroll.payment_gateway.payment_gateway_config.PayrollConfig')
    def test_initialize_payment_gateway_without_payment_point(self, mock_payroll_config):
        # Set up default gateway configuration
        mock_payroll_config.payment_gateway_class = 'payroll.tests.strategy_online_payment_tests.DefaultPaymentGatewayConnector'
        
        # Initialize without a payment point
        StrategyOnlinePayment.initialize_payment_gateway()
        
        # Check if the correct gateway connector is used
        self.assertIsInstance(StrategyOnlinePayment.PAYMENT_GATEWAY, DefaultPaymentGatewayConnector)

    @override_settings(PAYMENT_GATEWAYS=CUSTOM_PAYMENT_GATEWAYS)
    def test_initialize_payment_gateway_with_custom_payment_point(self):
        # Initialize with a payment point that has custom configuration
        StrategyOnlinePayment.initialize_payment_gateway(self.mock_custom_payment_point)
        
        # Check if the correct gateway connector is used
        self.assertIsInstance(StrategyOnlinePayment.PAYMENT_GATEWAY, CustomPaymentGatewayConnector)

    @override_settings(PAYMENT_GATEWAYS=CUSTOM_PAYMENT_GATEWAYS)
    @patch('payroll.strategies.strategy_online_payment.StrategyOnlinePayment._send_payment_data_to_gateway')
    def test_make_payment_with_custom_payment_point(self, mock_send_payment):
        # Initialize with custom payment point
        StrategyOnlinePayment.initialize_payment_gateway(self.mock_custom_payment_point)
        
        # Create mock payroll and user
        mock_payroll = MagicMock()
        mock_user = MagicMock()
        
        # Call make_payment_for_payroll method
        StrategyOnlinePayment.make_payment_for_payroll(mock_payroll, mock_user)
        
        # Verify that _send_payment_data_to_gateway was called with the right parameters
        mock_send_payment.assert_called_once_with(mock_payroll, mock_user)

if __name__ == '__main__':
    unittest.main()
