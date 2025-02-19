from rest_framework import serializers
from .models import BenefitConsumption, BenefitConsumptionStatus

class IndividualPaymentRequestSerializer(serializers.ModelSerializer):
    province = serializers.CharField(source="individual.groupindividuals.group.location.parent.parent.name", read_only=True)
    commune = serializers.CharField(source="individual.groupindividuals.group.location.parent.name", read_only=True)
    colline = serializers.CharField(source="individual.groupindividuals.group.location.name", read_only=True)
    prenom = serializers.CharField(source="individual.first_name", read_only=True)
    nom = serializers.CharField(source="individual.last_name", read_only=True)
    num_cni = serializers.CharField(source="individual.json_ext.ci", read_only=True)
    telephone = serializers.CharField(source="json_ext.phoneNumber", read_only=True)
    naissance_date = serializers.DateField(source="individual.dob", read_only=True)
    genre = serializers.CharField(source="individual.json_ext.sexe", read_only=True)
    code = serializers.CharField(read_only=True)
    montant = serializers.DecimalField(source="amount", max_digits=10, decimal_places=0, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = BenefitConsumption
        fields = [
            "province", "commune", "colline", "prenom", "nom",
            "num_cni", "telephone", "naissance_date", "genre",
            "code", "montant", "status"
        ]


class IndividualPaymentRequestUpdateSerializer(serializers.Serializer):
    benefit_id = serializers.UUIDField(required=True)
    new_status = serializers.ChoiceField(
        choices=BenefitConsumptionStatus.choices,
        required=True
    )
    receipt = serializers.CharField(required=False, allow_blank=True)
    payment_date = serializers.DateField(required=False)
    transaction_id = serializers.CharField(required=False, allow_blank=True)
    amount_paid = serializers.DecimalField(
        max_digits=18, 
        decimal_places=2,
        required=False
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_new_status(self, value):
        """Validate the status transition is allowed"""
        allowed_status_updates = [
            BenefitConsumptionStatus.APPROVE_FOR_PAYMENT,
            BenefitConsumptionStatus.REJECTED,
        ]
        
        if value not in allowed_status_updates:
            raise serializers.ValidationError(
                f"Status update to '{value}' is not allowed. Allowed values: {allowed_status_updates}"
            )
        return value
    
    def validate(self, data):
        """Validate required fields based on status"""
        if data['new_status'] == BenefitConsumptionStatus.RECONCILED:
            if not data.get('receipt'):
                raise serializers.ValidationError({"receipt": "Receipt is required for PAID status"})
            if not data.get('payment_date'):
                raise serializers.ValidationError({"payment_date": "Payment date is required for PAID status"})
        
        if data['new_status'] == BenefitConsumptionStatus.REJECTED and not data.get('notes'):
            raise serializers.ValidationError({"notes": "Notes are required when rejecting a payment"})
            
        return data

class BulkIndividualPaymentRequestUpdateSerializer(serializers.Serializer):
    updates = IndividualPaymentRequestUpdateSerializer(many=True)